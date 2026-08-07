from django.utils import timezone
from rest_framework import exceptions, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditLog
from accounts.notifications import notify_access_code_issued
from clients.models import StaffPermission
from core.permissions import IsClientSubscriptionActive, TenantScopedQuerySetMixin
from tickets.models import ServiceReport

from .models import AccessCode, AccessCodeScope
from .serializers import (
    AccessCodeSerializer,
    CustomerHistoryEntrySerializer,
    EngineerHistoryEntrySerializer,
    KnowledgeBaseEntrySerializer,
)


class CanIssueAccessCodes(permissions.BasePermission):
    """
    Issuing a code hands someone access to material they otherwise
    couldn't reach, so it sits behind the same authority as releasing
    reports to customers -- the service layer, not every staff member.
    """

    message = "Your role doesn't have permission to issue access codes."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user.is_authenticated
            and user.has_staff_perm(StaffPermission.APPROVE_SERVICE_REPORT)
        )


class AccessCodeViewSet(TenantScopedQuerySetMixin, viewsets.ModelViewSet):
    """
    Issue, list, and revoke the time-limited codes that let people
    without accounts read the Knowledge Base or a customer's history.
    """

    queryset = AccessCode.objects.select_related("customer", "issued_by")
    serializer_class = AccessCodeSerializer
    permission_classes = [permissions.IsAuthenticated, CanIssueAccessCodes, IsClientSubscriptionActive]

    # No update/partial_update: a code's scope, expiry, and target
    # shouldn't drift after it's been handed to someone. Revoke it and
    # issue a new one instead -- that leaves an honest trail of what
    # was granted when.
    http_method_names = ["get", "post", "delete", "head", "options"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code, plaintext_secret = AccessCode.issue(
            client=request.user.client,
            scope=serializer.validated_data["scope"],
            label=serializer.validated_data["label"],
            expires_at=serializer.validated_data["expires_at"],
            issued_by=request.user,
            customer=serializer.validated_data.get("customer"),
            max_uses=serializer.validated_data.get("max_uses"),
            recipient_email=serializer.validated_data.get("recipient_email", ""),
        )
        if code.recipient_email:
            notify_access_code_issued(code, plaintext_secret)

        AuditLog.objects.create(
            client=request.user.client,
            actor=request.user,
            action="access_code.issued",
            target_type="AccessCode",
            target_id=str(code.id),
            metadata={"scope": code.scope, "label": code.label, "expires_at": code.expires_at.isoformat()},
        )

        data = AccessCodeSerializer(code, context=self.get_serializer_context()).data
        # The ONLY time the secret is ever returned. Flagged explicitly
        # so whoever built the UI knows to show it prominently -- there
        # is no "view it again later".
        data["secret"] = plaintext_secret
        data["secret_notice"] = "Copy this now -- it can't be retrieved again. Issue a new code if it's lost."
        return Response(data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        """
        Revokes rather than deletes. A deleted code leaves no record
        that access was ever granted -- which is the opposite of what
        you want when someone asks "who had access to this, and when?"
        """
        if instance.revoked_at is None:
            instance.revoked_at = timezone.now()
            instance.save(update_fields=["revoked_at"])
            AuditLog.objects.create(
                client=instance.client,
                actor=self.request.user,
                action="access_code.revoked",
                target_type="AccessCode",
                target_id=str(instance.id),
                metadata={"label": instance.label},
            )


class AccessCodeLoginView(APIView):
    """
    POST /api/access/login/ -- {username, secret}

    Exchanges a code for its contents in one shot. Deliberately NOT
    issuing a JWT: a code holder isn't a user, has no account, and
    should not end up with a token that other endpoints might honour.
    Every request re-presents the code, and every request re-checks
    expiry and revocation -- so revoking a code takes effect
    immediately rather than whenever some token happens to lapse.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        secret = (request.data.get("secret") or "").strip()

        generic = "That code isn't valid, or it has expired."
        code = AccessCode.objects.filter(username=username).select_related("client", "customer").first()
        # Same message whether the username is wrong or the secret is --
        # otherwise this becomes a way to discover valid usernames.
        if code is None or not code.verify_secret(secret):
            raise exceptions.AuthenticationFailed(generic)
        if not code.is_usable:
            raise exceptions.AuthenticationFailed(f"That code is {code.status}.")

        code.register_use()
        context = {"request": request}

        if code.scope == AccessCodeScope.KNOWLEDGE_BASE:
            entries = (
                ServiceReport.objects
                .filter(ticket__client_id=code.client_id, include_in_knowledge_base=True)
                .select_related("ticket")
            )
            return Response({
                "scope": code.scope,
                "label": code.label,
                "expires_at": code.expires_at,
                "entries": KnowledgeBaseEntrySerializer(entries, many=True, context=context).data,
            })

        if code.scope == AccessCodeScope.ENGINEER_HISTORY:
            # Full technical detail, not the customer-facing summary --
            # released_with_customer status doesn't matter here, since
            # this is for the engineer's own preparation, not something
            # the customer is meant to see either way.
            entries = (
                ServiceReport.objects
                .filter(ticket__created_by=code.customer)
                .select_related("ticket", "engineer")
            )
            return Response({
                "scope": code.scope,
                "label": code.label,
                "customer": code.customer.username if code.customer else None,
                "expires_at": code.expires_at,
                "entries": EngineerHistoryEntrySerializer(entries, many=True, context=context).data,
            })

        entries = (
            ServiceReport.objects
            .filter(ticket__created_by=code.customer, shared_with_customer_at__isnull=False)
            .select_related("ticket")
        )
        return Response({
            "scope": code.scope,
            "label": code.label,
            "customer": code.customer.username if code.customer else None,
            "expires_at": code.expires_at,
            "entries": CustomerHistoryEntrySerializer(entries, many=True, context=context).data,
        })


class KnowledgeBaseViewSet(TenantScopedQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    """
    The Knowledge Base as seen by LOGGED-IN staff (interns using a code
    go through AccessCodeLoginView instead). Read-only: entries are
    created by flagging a service report, not written here.
    """

    serializer_class = KnowledgeBaseEntrySerializer
    permission_classes = [permissions.IsAuthenticated, IsClientSubscriptionActive]
    tenant_field = "ticket__client"

    def get_queryset(self):
        user = self.request.user
        # Requires an explicit permission, which Field Engineers do NOT
        # hold by default. Two separate reasons, both the company's own:
        #   - Customers have no business in training material at all.
        #   - The engineer who filmed a site shouldn't retain a
        #     browsable library of customer premises afterwards.
        # Interns reach this through a time-limited access code
        # (AccessCodeLoginView), never through a standing login.
        if user.client_id is None or not user.has_staff_perm(StaffPermission.VIEW_KNOWLEDGE_BASE):
            return ServiceReport.objects.none()
        return (
            ServiceReport.objects
            .filter(ticket__client_id=user.client_id, include_in_knowledge_base=True)
            .select_related("ticket")
        )
