import uuid

from django.conf import settings
from django.db import models


class TicketStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In Progress"
    ON_HOLD = "on_hold", "On Hold"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class TicketPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


def ticket_attachment_upload_path(instance, filename):
    return f"ticket_files/{instance.client_id}/{instance.id}/{filename}"


class Ticket(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Denormalized: `client` is technically derivable via
    # created_by.client, but we store it directly on Ticket. Reasons:
    # 1. Every tenant-scoped model having a *direct* `client` FK means
    #    TenantScopedQuerySetMixin's default `tenant_field = "client"`
    #    works out of the box here, instead of every Ticket query paying
    #    for a join through created_by -> User -> Client.
    # 2. It's one indexed column you can filter/aggregate on directly
    #    (see the composite indexes below) for dashboards and reports.
    # Kept in sync automatically in save() below, so it never drifts.
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="tickets")

    title = models.CharField(max_length=255)
    description = models.TextField()
    product_or_service = models.CharField(
        max_length=255,
        blank=True,
        help_text="Free-text reference to the product/service this ticket concerns.",
    )

    status = models.CharField(max_length=20, choices=TicketStatus.choices, default=TicketStatus.OPEN)
    priority = models.CharField(max_length=20, choices=TicketPriority.choices, default=TicketPriority.MEDIUM)

    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="tickets_created",
        limit_choices_to={"role": "sub_client"},
    )
    assigned_to = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets_assigned",
        limit_choices_to={"role": "support_staff"},
    )

    # Attached when the ticket is RAISED, not later. Customers get one
    # file and one video at that moment and then the thread is
    # conversation only -- the client's rule, and a sound one: evidence
    # belongs with the original report, not scattered through a chat.
    attachment = models.FileField(upload_to=ticket_attachment_upload_path, max_length=255, null=True, blank=True)
    attachment_filename = models.CharField(max_length=255, blank=True)
    video = models.FileField(upload_to=ticket_attachment_upload_path, max_length=255, null=True, blank=True)
    video_filename = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["client", "status"]),
            models.Index(fields=["client", "assigned_to"]),
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.client_id and self.created_by_id:
            self.client_id = self.created_by.client_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.client.name}] {self.title}"


def ticket_comment_attachment_upload_path(instance, filename):
    # Namespaced by ticket + client ID so two tickets' files never
    # collide, and a directory listing alone never mixes files across
    # tenants even at the filesystem level.
    return f"ticket_attachments/{instance.ticket.client_id}/{instance.ticket_id}/{filename}"


class TicketComment(models.Model):
    """
    The conversation history on a ticket -- customer messages, staff
    replies, and internal-only notes.

    `attachment` lives directly on the comment (rather than as a
    separate TicketAttachment model linked only to the Ticket) on
    purpose: a file is something someone attaches to a SPECIFIC
    message ("here's a screenshot of the error"), not a free-floating
    thing loosely associated with the ticket as a whole. Folding it
    into the comment itself means:
    - The file and the message it belongs to can never drift apart --
      they're the same row, always rendered together.
    - `is_internal_note` automatically covers the attachment too, for
      free. A Sub-Client is already blocked from seeing internal
      comments (see TicketCommentViewSet.get_queryset) -- since the
      file lives on that same row, there's no separate check needed to
      also hide an internal comment's attachment from them.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="ticket_comments")
    body = models.TextField()

    # Optional file attached to this specific message. max_length
    # raised from Django's 100-char default -- the upload path
    # includes two UUIDs before the filename even starts, which blows
    # past 100 characters for any real filename (confirmed this failed
    # with a real upload before this fix was in place, back when this
    # lived on the old separate TicketAttachment model).
    attachment = models.FileField(
        upload_to=ticket_comment_attachment_upload_path, max_length=255, null=True, blank=True,
    )
    attachment_filename = models.CharField(max_length=255, blank=True)

    # Separate field rather than reusing `attachment`, so a single
    # message can carry BOTH a document and a screen recording -- and
    # so each can have its own size limit (video needs far more room
    # than a screenshot; see TicketCommentSerializer). Both are
    # optional; only the message text itself is required.
    video = models.FileField(
        upload_to=ticket_comment_attachment_upload_path, max_length=255, null=True, blank=True,
    )
    video_filename = models.CharField(max_length=255, blank=True)

    # Staff-only notes (e.g. internal escalation context) that must
    # never be serialized back to a Sub-Client. Filtered out in the
    # viewset's get_queryset for sub_client users, not just hidden in
    # the frontend -- the backend must not send this data to that role
    # at all.
    is_internal_note = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author} on ticket {self.ticket_id}"


class TicketStatusHistory(models.Model):
    """
    Records every status transition a ticket goes through -- separate
    from AuditLog (which already records reassignment) because this is
    structured, per-ticket data a report can aggregate directly
    (average time in each status, etc.), rather than something to
    parse out of a generic action-log's free-text metadata.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=20, choices=TicketStatus.choices, null=True, blank=True)
    to_status = models.CharField(max_length=20, choices=TicketStatus.choices)
    changed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="ticket_status_changes"
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at"]
        verbose_name_plural = "Ticket status histories"

    def __str__(self):
        return f"Ticket {self.ticket_id}: {self.from_status} -> {self.to_status}"



def service_report_video_upload_path(instance, filename):
    return f"service_reports/{instance.ticket.client_id}/{instance.ticket_id}/{filename}"


class ServiceReport(models.Model):
    """
    The document a Field Engineer produces after attending a site.

    Deliberately TWO-TIER, because the internal record and what the
    customer should receive are genuinely different documents:

      Internal (engineer -> service layer)
        Everything: what was actually done, the root cause, parts
        consumed, blunt internal notes, and the service video. This is
        the training material and the real record.

      Customer-facing (service layer -> customer)
        Only `customer_summary`, written by the service layer after
        reviewing the above -- deliberately NOT auto-generated from it.
        A customer shouldn't receive raw internal commentary ("their
        server room is a mess", "third failure this year, upsell them")
        or a video of an engineer's hands inside their equipment. The
        service layer decides what's appropriate to say.

    That split is enforced in the serializer, not just hidden in the
    UI -- a customer hitting the API directly still only ever receives
    the summary. See ServiceReportSerializer.to_representation.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # OneToOne rather than FK: one visit produces one report. A second
    # visit for the same problem is a status change and more work logged
    # on the same report, not a competing second document.
    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name="service_report")
    engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="service_reports"
    )

    # --- Internal detail: never leaves the service organisation -----
    work_performed = models.TextField(help_text="What was actually done on site, in detail.")
    root_cause = models.TextField(blank=True, help_text="Why the problem happened.")
    parts_used = models.TextField(blank=True, help_text="Parts replaced or consumed.")
    internal_notes = models.TextField(blank=True, help_text="Staff-only observations. Never shown to the customer.")
    service_video = models.FileField(
        upload_to=service_report_video_upload_path, max_length=255, null=True, blank=True,
        help_text="On-site recording. Internal only -- used for training, never sent to the customer.",
    )
    service_video_filename = models.CharField(max_length=255, blank=True)
    # A human title for the recording, so the training library is
    # browsable by topic rather than by meaningless camera filenames
    # ("IMG_0042.mp4"). Required whenever a video is attached --
    # enforced in ServiceReportSerializer.validate.
    video_title = models.CharField(
        max_length=200, blank=True,
        help_text="What the recording shows, e.g. 'Replacing a fuser unit on an HP M404'.",
    )

    # --- Customer-facing summary ------------------------------------
    customer_summary = models.TextField(
        blank=True,
        help_text="Short, plain-language summary written by the service layer for the customer.",
    )
    summarised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="service_reports_summarised",
    )
    shared_with_customer_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Set when the summary is released. Until then the customer sees nothing.",
    )

    # Opt-in flag for the knowledge base, so a routine job doesn't
    # clutter training material and a sensitive one is never added by
    # accident. Deliberately a decision someone makes, not a default.
    include_in_knowledge_base = models.BooleanField(
        default=False,
        help_text="Make this report's video available as internal training material.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Service report for {self.ticket.title}"

    @property
    def is_shared_with_customer(self):
        return self.shared_with_customer_at is not None


class HistoryAccessRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    DENIED = "denied", "Denied"


class HistoryAccessRequest(models.Model):
    """
    An engineer ASKING for temporary access to a customer's history --
    as opposed to knowledge.AccessCode, which is the Service Manager
    proactively ISSUING one. Before this, only the manager could
    initiate the grant; an engineer preparing for a job had no way to
    ask for what they needed, and had to hope someone thought of it.

    Deliberately a request, not a direct grant -- the engineer doesn't
    hold ASSIGN/APPROVE-level authority, so they can't issue the code
    themselves; the Service Manager still decides. Approving creates a
    real knowledge.AccessCode under the hood, scoped to
    ENGINEER_HISTORY (see that model) -- full technical detail, not
    the customer-facing summary a customer's own code would show.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="history_access_requests")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="history_access_requests"
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="history_access_requests_about"
    )
    status = models.CharField(max_length=20, choices=HistoryAccessRequestStatus.choices, default=HistoryAccessRequestStatus.PENDING)
    reason = models.CharField(max_length=255, blank=True, help_text="Why the engineer needs this, e.g. 'repeat fault'.")

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="history_access_requests_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    # Set only once approved -- links to the actual credential that was
    # issued, so "who had access to what, and via which request" stays
    # traceable from one place.
    access_code = models.ForeignKey(
        "knowledge.AccessCode", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.requested_by} requesting {self.customer}'s history ({self.status})"
