import datetime
import secrets
import uuid

from django.db import models
from django.utils import timezone


class AccessCodeScope(models.TextChoices):
    """
    What a code unlocks. Three genuinely different audiences:

      KNOWLEDGE_BASE -- interns being trained. They see service
          recordings and write-ups, across all customers, but nothing
          identifying a specific customer's account.
      CUSTOMER_HISTORY -- one specific customer looking at their own
          service history. Scoped to exactly one customer, and shows
          only the customer-facing summary -- the same cut a logged-in
          customer would see.
      ENGINEER_HISTORY -- a Field Engineer preparing for a job,
          approved via a HistoryAccessRequest. Also scoped to one
          customer, but shows the FULL technical record (what was
          done, root cause, parts used) rather than the summary --
          useless for an engineer trying to avoid re-diagnosing a
          repeat fault from scratch. Still excludes internal_notes,
          which is a different kind of content (staff commentary, not
          technical detail) not part of what was asked for here.
    """

    KNOWLEDGE_BASE = "knowledge_base", "Knowledge Base (training material)"
    CUSTOMER_HISTORY = "customer_history", "Customer service history"
    ENGINEER_HISTORY = "engineer_history", "Full technical history (for an engineer preparing a job)"


class AccessCode(models.Model):
    """
    A time-limited credential for someone who has no account at all --
    typically an intern being trained, or a customer contact who only
    needs to read their own service history.

    Why not just create them a normal user account? Because these are
    temporary, external people. A real account has a permanent
    username, a resettable password, a role, and lives in the tenant's
    user list forever. An intern on a six-week placement doesn't need
    any of that, and cleaning up forgotten accounts afterwards is
    exactly how stale logins accumulate. A code that stops working on
    a set date solves it without leaving anything behind.

    Security properties, mirroring the password-reset OTP work:
      - The secret is HASHED. Database access alone doesn't yield a
        working credential.
      - Hard expiry, set by whoever issued it.
      - Revocable instantly, independent of expiry.
      - Optional use cap, for "watch this once" situations.
      - READ-ONLY by design. A code can never write anything -- see
        the viewsets, which are ReadOnlyModelViewSet.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="access_codes")
    scope = models.CharField(max_length=32, choices=AccessCodeScope.choices)

    # Who it's for -- a label, not a login. Purely so the issuer can
    # tell their codes apart later ("Intern - Ramesh, Aug batch").
    label = models.CharField(max_length=150)

    # The visible half of the credential, safe to store in the clear.
    # Paired with a secret that isn't.
    username = models.CharField(max_length=64, unique=True)
    secret_hash = models.CharField(max_length=128)

    # Optional. Someone WITHOUT an account has no email tied to them in
    # the system the way a real User does -- this is purely so the
    # credential can be emailed directly (an intern's personal email,
    # say) instead of relying entirely on whoever issued it to relay
    # it by hand. Not required: the on-screen one-time reveal still
    # works fine without it.
    recipient_email = models.EmailField(blank=True)

    # Only set for CUSTOMER_HISTORY codes -- which customer's history
    # this unlocks. Null for knowledge-base codes, which aren't tied
    # to any one customer.
    customer = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, null=True, blank=True, related_name="access_codes",
    )

    issued_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="access_codes_issued",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    max_uses = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Optional cap on how many times this code can be used. Blank means unlimited until expiry.",
    )
    use_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.label} ({self.get_scope_display()})"

    @classmethod
    def issue(cls, *, client, scope, label, expires_at, issued_by, customer=None, max_uses=None, recipient_email=""):
        """
        Creates a code and returns (instance, plaintext_secret). The
        plaintext is returned ONCE so it can be handed over, and is
        never stored or recoverable afterwards -- if it's lost, issue
        a new one rather than trying to look the old one up.
        """
        from django.contrib.auth.hashers import make_password

        # A readable public half plus a strong secret half. The
        # username is deliberately human-friendly (it gets typed by
        # hand, often off a printed sheet); the secret carries all the
        # actual entropy.
        username = f"{scope.split('_')[0]}-{secrets.token_hex(3)}"
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I -- these get misread
        secret = "-".join(
            "".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)
        )
        code = cls.objects.create(
            client=client, scope=scope, label=label, username=username,
            secret_hash=make_password(secret), customer=customer,
            issued_by=issued_by, expires_at=expires_at, max_uses=max_uses,
            recipient_email=recipient_email,
        )
        return code, secret

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    @property
    def is_exhausted(self):
        return self.max_uses is not None and self.use_count >= self.max_uses

    @property
    def is_usable(self):
        return not (self.is_expired or self.is_revoked or self.is_exhausted)

    @property
    def status(self):
        """Human-readable state, for listing codes in the UI."""
        if self.is_revoked:
            return "revoked"
        if self.is_expired:
            return "expired"
        if self.is_exhausted:
            return "used up"
        return "active"

    def verify_secret(self, submitted):
        from django.contrib.auth.hashers import check_password

        return check_password(submitted, self.secret_hash)

    def register_use(self):
        self.use_count += 1
        self.last_used_at = timezone.now()
        self.save(update_fields=["use_count", "last_used_at"])
