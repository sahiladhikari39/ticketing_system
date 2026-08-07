from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.utils import timezone
from rest_framework import exceptions, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from audit.models import AuditLog
from clients.models import StaffPermission, SupportStaffProfile
from accounts.notifications import notify_service_report_released, notify_ticket_assigned
from core.permissions import IsClientSubscriptionActive

from .models import ServiceReport, Ticket, TicketComment, TicketStatusHistory
from .serializers import (
    ServiceReportSerializer,
    TicketCommentSerializer,
    TicketSerializer,
    TicketStatusHistorySerializer,
)

TERMINAL_STATUSES = ("resolved", "closed")


class TicketViewSet(viewsets.ModelViewSet):
    serializer_class = TicketSerializer
    permission_classes = [permissions.IsAuthenticated, IsClientSubscriptionActive]
    # Tickets carry a file and a video now, attached at creation time.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        """
        Two separate layers of filtering, and both matter:

        1. TENANT scope -- filter to the caller's own client. No Soori
           Admin bypass: a ticket is a Client's own operational data,
           not something the platform owner should see. Soori Admin has
           client_id=None, so they fall into the first branch below and
           get nothing back.
        2. ROLE scope -- a Sub-Client is one CUSTOMER of that company,
           not staff. They must only ever see tickets they personally
           raised, never a different customer's. Tenant scope alone
           does NOT give you this: two customers of the same company
           share a client_id, so without this second filter one
           customer sees the other's tickets. (That regression happened
           for real -- this filter was dropped when the Soori Admin
           bypass was removed, and a Sub-Client could see every ticket
           in their company until it was restored.)
        """
        user = self.request.user
        if user.client_id is None:
            return Ticket.objects.none()

        # select_related covers everything the serializer reads off a
        # related object -- without it, rendering a list of N tickets
        # fires a separate query per row for each of these (the classic
        # N+1 problem). created_by__sub_client_profile is needed for
        # the created_by_company field specifically.
        #
        # prefetch_related handles the REVERSE relations (comments and
        # status history), which select_related can't -- those are
        # one-to-many, not one-to-one. Measured before adding this:
        # 32 tickets took 74 queries and grew by 2 per extra ticket.
        # After: flat, regardless of how many tickets come back.
        qs = Ticket.objects.filter(client_id=user.client_id).select_related(
            "client", "created_by", "created_by__sub_client_profile", "assigned_to", "service_report"
        ).prefetch_related(
            "comments", "comments__author", "status_history", "status_history__changed_by"
        )

        if user.role == "sub_client":
            qs = qs.filter(created_by=user)
        elif user.role == "support_staff" and not user.has_staff_perm(StaffPermission.ASSIGN_TICKETS):
            # A Field Engineer (or any custom role without assignment
            # authority) should see only the work actually handed to
            # them -- not the whole company's queue. Someone who CAN
            # assign tickets (Service Department) needs full visibility
            # to do that job; this branch is specifically for those who
            # can't. Confirmed this was a real gap: every support_staff
            # member, including engineers, previously saw every ticket
            # at the company regardless of assignment.
            qs = qs.filter(assigned_to=user)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        # Server sets client + created_by -- never trust these from the
        # request body (see the read_only_fields note in the serializer).
        serializer.save(created_by=user, client_id=user.client_id)

    def perform_update(self, serializer):
        """
        Three things happen here whenever a ticket is updated, all
        driven off comparing before/after:

        1. resolved_at is stamped the moment status FIRST enters a
           terminal state (resolved/closed) -- and cleared if it moves
           back OUT of one (e.g. reopened), so a ticket that was
           resolved-then-reopened doesn't quietly keep a stale
           resolved_at that would corrupt the average-resolution-time
           report below.
        2. Every actual status change is recorded in
           TicketStatusHistory -- structured, queryable history, not
           something to parse out of a free-text log.
        3. Reassignment is still recorded in AuditLog, same as before.
        """
        old_assigned_to_id = serializer.instance.assigned_to_id
        old_status = serializer.instance.status
        new_status = serializer.validated_data.get("status", old_status)

        extra = {}
        if new_status in TERMINAL_STATUSES and old_status not in TERMINAL_STATUSES:
            extra["resolved_at"] = timezone.now()
        elif new_status not in TERMINAL_STATUSES and old_status in TERMINAL_STATUSES:
            extra["resolved_at"] = None

        ticket = serializer.save(**extra)

        if ticket.status != old_status:
            TicketStatusHistory.objects.create(
                ticket=ticket, from_status=old_status, to_status=ticket.status, changed_by=self.request.user,
            )

        if ticket.assigned_to_id != old_assigned_to_id:
            AuditLog.objects.create(
                client=ticket.client,
                actor=self.request.user,
                action="ticket.reassigned",
                target_type="Ticket",
                target_id=str(ticket.id),
                metadata={
                    "assigned_to": str(ticket.assigned_to_id) if ticket.assigned_to_id else None,
                    "assigned_to_username": ticket.assigned_to.username if ticket.assigned_to_id else None,
                },
            )
            # Only when there's an actual assignee -- an unassignment
            # (assigned_to going back to None) has nobody to notify.
            if ticket.assigned_to_id:
                notify_ticket_assigned(ticket, ticket.assigned_to)

    def destroy(self, request, *args, **kwargs):
        # Deleting a ticket erases history a Client Admin might need to
        # review later -- a Sub-Client raising and tracking their own
        # ticket shouldn't be able to make it disappear entirely.
        if request.user.role == "sub_client":
            raise exceptions.PermissionDenied("Only Support Staff or a Client Admin can delete a ticket.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="nearby-engineers")
    def nearby_engineers(self, request, pk=None):
        """
        GET /api/tickets/<id>/nearby-engineers/

        Returns every Field Engineer at this company, ordered so the
        ones covering the customer's own area come first. This is what
        makes "send someone near the customer" practical -- otherwise
        a coordinator is picking from an unordered list and has to
        remember who covers where.

        Deliberately returns EVERYONE rather than only area matches:
        the nearest engineer might be busy, on leave, or the customer's
        area might not be covered at all. Hiding the rest would turn a
        helpful default into a dead end. The manager still decides.
        """
        ticket = self.get_object()  # 404s if outside the caller's tenant

        customer_profile = getattr(ticket.created_by, "sub_client_profile", None)
        customer_area = (getattr(customer_profile, "service_area", "") or "").strip().lower()

        # Selected by PERMISSION rather than role name, so a custom
        # role granted tickets.receive shows up here automatically.
        engineers = [
            p for p in SupportStaffProfile.objects
            .filter(user__client_id=ticket.client_id, is_active_agent=True)
            .select_related("user", "role")
            if p.role and p.role.has_perm(StaffPermission.RECEIVE_TICKETS)
        ]

        rows = []
        for eng in engineers:
            area = (eng.service_area or "").strip()
            rows.append({
                "user": str(eng.user_id),
                "username": eng.user.username,
                "full_name": eng.user.get_full_name(),
                "service_area": area,
                "role_name": eng.role.name if eng.role else "",
                "is_in_customer_area": bool(customer_area) and area.lower() == customer_area,
            })

        # Matching area first, then alphabetically inside each group so
        # the ordering is stable and predictable rather than arbitrary.
        rows.sort(key=lambda r: (not r["is_in_customer_area"], r["username"].lower()))

        return Response({
            "customer_area": getattr(customer_profile, "service_area", "") or "",
            "engineers": rows,
        })

    @action(detail=False, methods=["get"], url_path="reports")
    def reports(self, request):
        """
        GET /api/tickets/reports/ -- aggregate stats for a dashboard:
        ticket counts by status, average resolution time, and a
        per-Support-Staff breakdown of assigned vs resolved counts.
        Not for Sub-Clients -- these are org-wide numbers, not
        something about their own single ticket.
        """
        if not request.user.has_staff_perm(StaffPermission.VIEW_REPORTS):
            raise exceptions.PermissionDenied("Your role doesn't have permission to view reports.")

        qs = self.get_queryset()  # already correctly tenant/role scoped

        status_counts = {row["status"]: row["count"] for row in qs.values("status").annotate(count=Count("id"))}

        resolved_qs = qs.filter(resolved_at__isnull=False).annotate(
            resolution_time=ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
        )
        avg_duration = resolved_qs.aggregate(avg=Avg("resolution_time"))["avg"]
        avg_resolution_hours = round(avg_duration.total_seconds() / 3600, 1) if avg_duration else None

        by_staff = list(
            qs.exclude(assigned_to__isnull=True)
            .values("assigned_to", "assigned_to__username")
            .annotate(
                assigned_count=Count("id"),
                resolved_count=Count("id", filter=Q(status__in=TERMINAL_STATUSES)),
            )
            .order_by("-assigned_count")
        )

        return Response({
            "status_counts": status_counts,
            "avg_resolution_hours": avg_resolution_hours,
            "resolved_ticket_count": sum(status_counts.get(s, 0) for s in TERMINAL_STATUSES),
            "open_ticket_count": sum(v for k, v in status_counts.items() if k not in TERMINAL_STATUSES),
            "by_staff": [
                {
                    "staff_id": row["assigned_to"],
                    "username": row["assigned_to__username"],
                    "assigned_count": row["assigned_count"],
                    "resolved_count": row["resolved_count"],
                }
                for row in by_staff
            ],
        })


class TicketCommentViewSet(viewsets.ModelViewSet):
    serializer_class = TicketCommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsClientSubscriptionActive]
    # Needs BOTH: MultiPartParser/FormParser for when a comment carries
    # a file (the browser sends multipart/form-data for that), and
    # JSONParser still, for a plain text-only reply with no file --
    # the frontend sends plain JSON in that case rather than paying for
    # a multipart encode when there's nothing to attach.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        user = self.request.user
        if user.client_id is None:
            return TicketComment.objects.none()
        qs = TicketComment.objects.filter(ticket__client_id=user.client_id)

        if user.role == "sub_client":
            # Two restrictions, not one: never internal staff notes,
            # AND only on tickets they personally raised. Without that
            # second clause a customer could read the conversation on
            # a DIFFERENT customer's ticket at the same company.
            qs = qs.filter(is_internal_note=False, ticket__created_by=user)
        elif user.role == "support_staff" and not user.has_staff_perm(StaffPermission.ASSIGN_TICKETS):
            # Mirrors TicketViewSet.get_queryset -- an engineer who
            # can't see a ticket shouldn't be able to read its
            # conversation either.
            qs = qs.filter(ticket__assigned_to=user)

        return qs

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class ServiceReportViewSet(viewsets.ModelViewSet):
    """
    The engineer's report on a completed site visit, plus the
    separately-approved summary that goes back to the customer.
    """

    serializer_class = ServiceReportSerializer
    permission_classes = [permissions.IsAuthenticated, IsClientSubscriptionActive]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        user = self.request.user
        if user.client_id is None:
            return ServiceReport.objects.none()

        qs = ServiceReport.objects.filter(ticket__client_id=user.client_id).select_related(
            "ticket", "engineer", "summarised_by"
        )

        # A Field Engineer sees only the reports THEY wrote -- not the
        # service history of every customer in the company.
        #
        # This is the company's own stated requirement, and the reason
        # matters: engineers leave. If their normal login granted
        # standing access to all customer records, an engineer walking
        # out the door has been browsing the full customer base for
        # however long they worked there. When they genuinely need a
        # customer's history for a job, the service layer issues a
        # time-limited access code instead -- which expires on its own.
        if not user.has_staff_perm(StaffPermission.VIEW_ALL_SERVICE_REPORTS) and user.role != "sub_client":
            qs = qs.filter(engineer=user)

        if user.role == "sub_client":
            # Only reports on their OWN tickets, and only once released.
            # Two conditions, because tenant scope alone would show
            # them another customer's report, and no shared filter
            # would show them a draft mid-write.
            qs = qs.filter(ticket__created_by=user, shared_with_customer_at__isnull=False)

        return qs

    def perform_create(self, serializer):
        serializer.save(engineer=self.request.user)

    def perform_update(self, serializer):
        # Record WHO wrote the customer-facing wording, since that's
        # the person accountable for what the customer was told.
        extra = {}
        if "customer_summary" in serializer.initial_data:
            extra["summarised_by"] = self.request.user
        serializer.save(**extra)

    @action(detail=True, methods=["post"], url_path="release-to-customer")
    def release_to_customer(self, request, pk=None):
        """
        POST /api/service-reports/<id>/release-to-customer/

        A deliberate, separate step rather than something that happens
        automatically when a summary is typed. Releasing is the moment
        information leaves the organisation, and it should take an
        explicit decision -- not be a side effect of saving a draft.
        """
        report = self.get_object()

        if not request.user.has_staff_perm(StaffPermission.APPROVE_SERVICE_REPORT):
            raise exceptions.PermissionDenied("Your role can't release reports to customers.")

        if not (report.customer_summary or "").strip():
            raise exceptions.ValidationError({
                "customer_summary": "Write a customer summary before releasing this report."
            })

        if report.is_shared_with_customer:
            return Response(
                {"detail": "This report has already been shared with the customer."},
                status=status.HTTP_200_OK,
            )

        report.shared_with_customer_at = timezone.now()
        report.save(update_fields=["shared_with_customer_at"])

        AuditLog.objects.create(
            client=report.ticket.client,
            actor=request.user,
            action="service_report.released",
            target_type="ServiceReport",
            target_id=str(report.id),
            metadata={"ticket_id": str(report.ticket_id)},
        )
        notify_service_report_released(report)

        return Response({"detail": "Summary released to the customer."}, status=status.HTTP_200_OK)
