import datetime
import secrets
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

from .managers import UserManager


class Role(models.TextChoices):
    SOORI_ADMIN = "soori_admin", "Soori Admin"
    CLIENT_ADMIN = "client_admin", "Client Admin"
    SUPPORT_STAFF = "support_staff", "Support Staff"
    SUB_CLIENT = "sub_client", "Sub-Client"


class User(AbstractUser):
    """
    ONE custom User model shared by all four roles, distinguished by `role`.

    Why one model instead of four separate ones (SooriAdmin, ClientAdmin,
    SupportStaffUser, SubClientUser)?

    Arguments for a single model + role field (what we did):
    - Auth machinery (login, password hashing, sessions, DRF token/JWT
      auth, `request.user`, permission checks) is built around exactly
      ONE user table in Django. Four separate models means either four
      separate auth backends, or an ugly shadow "identity" table anyway.
    - Every tenant-scoped model in the system (Ticket.created_by,
      Ticket.assigned_to, AuditLog.actor, ...) needs to point at "a user
      who belongs to a client". With one model, that's a single FK type.
      With four models, those FKs would need to be polymorphic (generic
      foreign keys, or four nullable FK columns per relation) -- notably
      worse for query performance and migrations.
    - Tenant scoping collapses to one rule everywhere: `user.client_id`.

    Trade-off you accept: the User table carries a `client` FK that's
    always null for Soori Admins, and role-specific fields (support
    staff's seniority tier, sub-client's company name) don't belong here.
    We solve that by keeping User "thin" (identity + auth + role + tenant)
    and pushing role-specific data into one-to-one profile models
    (SupportStaffProfile, SubClientProfile in the `clients` app). This is
    the standard "shared identity table + role profile" pattern.

    When would separate models per role be the better call instead?
    If the roles never shared an auth mechanism (e.g. Sub-Clients log in
    via a magic email link while staff use SSO) or if you truly never
    need to query "all users regardless of role" you might reach for
    separate models to get stricter, role-specific NOT NULL columns at
    the DB level. Your spec has all 4 roles doing username/password
    against one platform, so a single model is simpler and more
    idiomatic here.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=Role.choices)

    # Null ONLY for Soori Admin (platform-level, no tenant). Required for
    # the other 3 roles. Enforced in clean() at the app level, and backed
    # by a CheckConstraint at the DB level as defense-in-depth.
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users",
        help_text="Tenant this user belongs to. Null only for Soori Admins.",
    )

    email = models.EmailField(unique=True)

    REQUIRED_FIELDS = ["email"]

    objects = UserManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                # Django 5.1+ renamed the kwarg from `check` to `condition`.
                # If you're on an older Django, use `check=` instead.
                condition=(
                    models.Q(role=Role.SOORI_ADMIN, client__isnull=True)
                    | (~models.Q(role=Role.SOORI_ADMIN) & models.Q(client__isnull=False))
                ),
                name="soori_admin_has_no_client_others_require_client",
            )
        ]

    def clean(self):
        super().clean()
        if self.role == Role.SOORI_ADMIN and self.client_id is not None:
            raise ValidationError("Soori Admin users must not belong to a Client.")
        if self.role != Role.SOORI_ADMIN and self.client_id is None:
            raise ValidationError(f"{self.get_role_display()} users must belong to a Client.")

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"

    def soft_delete(self):
        """
        Removes someone's ability to use Soori, WITHOUT destroying the
        history attached to them.

        Why not just delete the row outright? Because several
        foreign keys pointing at User use on_delete=CASCADE:
          - Ticket.created_by      -> deleting a Sub-Client would
                                      delete every ticket they ever
                                      raised
          - TicketComment.author   -> deleting anyone would delete
                                      every reply they ever wrote,
                                      gutting conversation history
        Confirmed both directly. A hard delete would silently destroy
        real support history, which is a worse outcome than the bug it
        would be fixing.

        So instead this does three things:
        1. is_active = False -- Django's auth system refuses login for
           an inactive user, so a removed person genuinely cannot get
           back in. (Before this existed, a "removed" staff member
           could still log in and read the whole company's tickets --
           confirmed with a real test.)
        2. Renames username/email to a one-off "deleted_..." form,
           which RELEASES the original username and email so they can
           be reused for a new account immediately.
        3. Keeps the row itself, so every ticket, comment, and audit
           entry that points at this person still resolves.

        Deliberately NOT reversible via the API -- undoing this would
        need the original username/email back, which may since have
        been taken by someone else.
        """
        suffix = uuid.uuid4().hex[:8]
        self.is_active = False
        self.username = f"deleted_{suffix}_{self.username}"[:150]
        if self.email:
            self.email = f"deleted_{suffix}_{self.email}"[:254]
        self.save(update_fields=["is_active", "username", "email"])

    def has_staff_perm(self, code):
        """
        The single place anything asks "is this person allowed to X".

        Two shortcuts before the role lookup, both deliberate:
          - A Client Admin (Service Manager) implicitly has every
            permission inside their own company. They're the one who
            configures the roles in the first place, so a manager
            locking themselves out by editing a role would be an
            absurd failure mode.
          - Everyone else without a staff profile (customers, Soori
            Admin) has none of these -- these permissions only
            describe work INSIDE a company's service team.
        """
        if self.role == Role.CLIENT_ADMIN:
            return True
        profile = getattr(self, "staff_profile", None)
        if profile is None or profile.role_id is None:
            return False
        return profile.role.has_perm(code)

    @property
    def is_soori_admin(self):
        return self.role == Role.SOORI_ADMIN

    @property
    def is_client_admin(self):
        return self.role == Role.CLIENT_ADMIN

    @property
    def is_support_staff(self):
        return self.role == Role.SUPPORT_STAFF

    @property
    def is_sub_client(self):
        return self.role == Role.SUB_CLIENT


class PasswordResetOTP(models.Model):
    """
    A short-lived, single-use numeric code emailed to someone who's
    forgotten their password.

    Chosen over the emailed-link approach because a link has to embed
    an absolute URL to the frontend -- which means it breaks the moment
    the frontend moves, and looks broken in dev (a "localhost" link in
    a real inbox). A code has no URL in it at all, so it works
    identically no matter where anything is hosted.

    Security properties, none of which are optional for something that
    grants account access:
      - The code is HASHED, never stored in readable form. Anyone with
        database access still can't use a pending reset.
      - 10-minute expiry. Six digits is only a million combinations,
        so the window matters.
      - Single use -- marked used the moment it succeeds.
      - Attempt-capped (MAX_ATTEMPTS). Without this, a million guesses
        against a 6-digit code is entirely feasible for a script.
      - Requesting a new code invalidates any earlier pending one, so
        old emails stop working immediately.
    """

    CODE_LENGTH = 6
    EXPIRY_MINUTES = 10
    MAX_ATTEMPTS = 5

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="password_reset_otps")
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Reset code for {self.user.username} ({'used' if self.used_at else 'pending'})"

    @classmethod
    def generate_for(cls, user):
        """
        Creates a fresh code and returns (instance, plaintext_code).
        The plaintext is returned ONCE, purely so it can be emailed --
        it is never stored anywhere and can't be recovered afterwards.
        """
        from django.contrib.auth.hashers import make_password
        from django.utils import timezone as tz

        # Any earlier pending code stops working the moment a new one
        # is issued -- otherwise requesting a second code would leave
        # two valid codes in circulation.
        cls.objects.filter(user=user, used_at__isnull=True).update(used_at=tz.now())

        # secrets, not random -- same reasoning as password generation.
        code = "".join(secrets.choice("0123456789") for _ in range(cls.CODE_LENGTH))
        otp = cls.objects.create(
            user=user,
            code_hash=make_password(code),
            expires_at=tz.now() + datetime.timedelta(minutes=cls.EXPIRY_MINUTES),
        )
        return otp, code

    @property
    def is_expired(self):
        from django.utils import timezone as tz

        return tz.now() > self.expires_at

    def verify(self, submitted_code):
        """
        Returns (ok, error_message). Increments the attempt counter on
        every wrong guess, and refuses further tries past MAX_ATTEMPTS.
        """
        from django.contrib.auth.hashers import check_password
        from django.utils import timezone as tz

        if self.used_at is not None:
            return False, "This code has already been used. Please request a new one."
        if self.is_expired:
            return False, "This code has expired. Please request a new one."
        if self.attempts >= self.MAX_ATTEMPTS:
            return False, "Too many incorrect attempts. Please request a new code."

        if not check_password(submitted_code, self.code_hash):
            self.attempts += 1
            self.save(update_fields=["attempts"])
            remaining = self.MAX_ATTEMPTS - self.attempts
            if remaining <= 0:
                return False, "Too many incorrect attempts. Please request a new code."
            return False, f"That code isn't right. {remaining} attempt(s) remaining."

        self.used_at = tz.now()
        self.save(update_fields=["used_at"])
        return True, None
