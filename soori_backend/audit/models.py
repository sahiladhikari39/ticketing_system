import uuid

from django.db import models


class AuditLog(models.Model):
    """
    Append-only record of actions taken within a Client's org, so a
    Client Admin can later review "who did what". Written by application
    code (e.g. in perform_create/perform_update of relevant viewsets, or
    signal handlers) -- never exposed as a writable API endpoint.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="audit_logs",
        null=True,
        blank=True,
        help_text="Null for platform-level (Soori Admin) actions with no single tenant.",
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_actions",
    )

    action = models.CharField(max_length=100, help_text="e.g. 'ticket.assigned', 'staff.role_changed'")
    target_type = models.CharField(max_length=100, blank=True, help_text="Model name of the affected object")
    target_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["client", "-created_at"])]

    def __str__(self):
        return f"{self.action} by {self.actor} @ {self.created_at:%Y-%m-%d %H:%M}"
