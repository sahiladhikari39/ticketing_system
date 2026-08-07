"""
Serializers and views for HistoryAccessRequest -- an engineer ASKING
for temporary access to a customer's full service history, as opposed
to knowledge.AccessCode which is the Service Manager proactively
issuing one. See HistoryAccessRequest's docstring in models.py for the
full reasoning.

Kept in its own module rather than folded into tickets/serializers.py
and tickets/views.py -- those files are already large, and this is a
genuinely separate concern (a request/approval workflow) from ticket
CRUD itself.
"""

import datetime

from django.utils import timezone
from rest_framework import exceptions, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.notifications import (
    notify_history_access_approved,
    notify_history_access_denied,
    notify_history_access_requested,
)
from clients.models import StaffPermission
from knowledge.models import AccessCode, AccessCodeScope

from .models import HistoryAccessRequest, HistoryAccessRequestStatus, Ticket


class HistoryAccessRequestSerializer(serializers.ModelSerializer):
    requested_by_username = serializers.CharField(source="requested_by.username", read_only=True)
    customer_username = serializers.CharField(source="customer.username", read_only=True)
    customer_company = serializers.SerializerMethodField()
    resolved_by_username = serializers.CharField(source="resolved_by.username", read_only=True, default=None)
    ticket_title = serializers.CharField(source="ticket.title", read_only=True)

    class Meta:
        model = HistoryAccessRequest
        fields = [
            "id", "ticket", "ticket_title", "requested_by", "requested_by_username",
            "customer", "customer_username", "customer_company", "reason",
            "status", "resolved_by", "resolved_by_username", "resolved_at", "created_at",
        ]
        read_only_fields = [
            "id", "requested_by", "customer", "status",
            "resolved_by", "resolved_at", "created_at",
        ]

    def get_customer_company(self, obj):
        profile = getattr(obj.customer, "sub_client_profile", None)
        return getattr(profile, "company_name", "") if profile else ""

    def validate_ticket(self, ticket):
        request = self.context["request"]
        user = request.user
        if ticket.client_id != user.client_id:
            raise serializers.ValidationError("You do not have access to this ticket.")
        # Only the ASSIGNED engineer requests history for a job -- not
        # any engineer at the company, and not for tickets that aren't
        # theirs to prepare for.
        if ticket.assigned_to_id != user.id:
            raise serializers.ValidationError("You can only request history for a ticket assigned to you.")
        return ticket

    def create(self, validated_data):
        ticket = validated_data["ticket"]
        request = self.context["request"]
        instance = HistoryAccessRequest.objects.create(
            ticket=ticket,
            requested_by=request.user,
            customer=ticket.created_by,
            reason=validated_data.get("reason", ""),
        )
        notify_history_access_requested(instance)
        return instance


class HistoryAccessRequestViewSet(viewsets.ModelViewSet):
    """
    Engineers create requests for tickets assigned to them; the
    Service Manager/Department (whoever can approve service reports --
    the same authority that reviews and releases them) sees every
    request at the company and approves or denies it.
    """

    serializer_class = HistoryAccessRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if user.client_id is None:
            return HistoryAccessRequest.objects.none()
        qs = HistoryAccessRequest.objects.filter(ticket__client_id=user.client_id).select_related(
            "ticket", "requested_by", "customer", "resolved_by"
        )
        # An engineer sees their OWN requests (so they can check status);
        # only someone who can approve sees everyone else's too.
        if not user.has_staff_perm(StaffPermission.APPROVE_SERVICE_REPORT):
            qs = qs.filter(requested_by=user)
        return qs

    def perform_create(self, serializer):
        serializer.save()

    def _resolve(self, request, pk, approve, hours=4):
        if not request.user.has_staff_perm(StaffPermission.APPROVE_SERVICE_REPORT):
            raise exceptions.PermissionDenied("Your role can't approve or deny access requests.")

        history_request = self.get_object()
        if history_request.status != HistoryAccessRequestStatus.PENDING:
            return Response(
                {"detail": f"This request was already {history_request.status}."},
                status=status.HTTP_200_OK,
            )

        history_request.resolved_by = request.user
        history_request.resolved_at = timezone.now()

        if approve:
            code, secret = AccessCode.issue(
                client=request.user.client,
                scope=AccessCodeScope.ENGINEER_HISTORY,
                label=f"{history_request.requested_by.username} - {history_request.customer.username} history",
                expires_at=timezone.now() + datetime.timedelta(hours=hours),
                issued_by=request.user,
                customer=history_request.customer,
            )
            history_request.status = HistoryAccessRequestStatus.APPROVED
            history_request.access_code = code
            history_request.save(update_fields=["status", "resolved_by", "resolved_at", "access_code"])
            notify_history_access_approved(history_request, code, secret)
            return Response({"detail": "Approved. The engineer has been emailed a temporary login."})

        history_request.status = HistoryAccessRequestStatus.DENIED
        history_request.save(update_fields=["status", "resolved_by", "resolved_at"])
        notify_history_access_denied(history_request)
        return Response({"detail": "Denied."})

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        hours = request.data.get("hours", 4)
        try:
            hours = max(1, int(hours))
        except (TypeError, ValueError):
            hours = 4
        return self._resolve(request, pk, approve=True, hours=hours)

    @action(detail=True, methods=["post"], url_path="deny")
    def deny(self, request, pk=None):
        return self._resolve(request, pk, approve=False)
