import uuid

from django.db import models
from django.utils import timezone


class SubscriptionPlan(models.TextChoices):
    BASIC = "basic", "Basic"
    PRO = "pro", "Pro"
    ENTERPRISE = "enterprise", "Enterprise"


class SubscriptionStatus(models.TextChoices):
    TRIAL = "trial", "Trial"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    CANCELLED = "cancelled", "Cancelled"


class SubscriptionPeriod(models.TextChoices):
    """
    A fixed set of billing terms, not an arbitrary date range someone
    has to calculate by hand. `subscription_end` is still a real
    stored date underneath (queries, reports, and "is this expired"
    checks all need an actual date) -- this is just what drives it,
    computed server-side in ClientSerializer.save() using calendar-
    correct month arithmetic (so "start Jan 31 + 1 month" lands on
    Feb 28, not some rough 30-day approximation).
    """

    ONE_MONTH = "1_month", "1 Month"
    THREE_MONTHS = "3_months", "3 Months"
    SIX_MONTHS = "6_months", "6 Months"
    ONE_YEAR = "1_year", "1 Year"


PERIOD_TO_MONTHS = {
    SubscriptionPeriod.ONE_MONTH: 1,
    SubscriptionPeriod.THREE_MONTHS: 3,
    SubscriptionPeriod.SIX_MONTHS: 6,
    SubscriptionPeriod.ONE_YEAR: 12,
}


class Client(models.Model):
    """
    A subscribing company -- the TENANT itself. This is the root of
    tenant isolation: every other tenant-scoped model (User,
    SupportStaffProfile, SubClientProfile, Ticket, AuditLog) traces a
    `client` FK back here, either directly or via a one-hop join.

    Fields below split cleanly into two groups:
    - Platform/billing fields (plan, status, subscription dates,
      contact/tax info) -- this IS what Soori Admin manages. It's the
      business relationship between Soori and the Client, not the
      Client's own product usage.
    - Everything else about how this company actually uses Soori
      (their tickets, their staff, their customers) lives on OTHER
      models, and Soori Admin deliberately has no access to any of it
      -- see TenantScopedQuerySetMixin's docstring in core/permissions.py.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)

    registered_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="clients_registered",
        limit_choices_to={"role": "soori_admin"},
        help_text="The Soori Admin who onboarded this client.",
    )

    plan = models.CharField(max_length=20, choices=SubscriptionPlan.choices, default=SubscriptionPlan.BASIC)
    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIAL)
    subscription_period = models.CharField(
        max_length=20, choices=SubscriptionPeriod.choices, default=SubscriptionPeriod.ONE_MONTH,
        help_text="Billing term. Drives subscription_end -- see ClientSerializer.",
    )
    subscription_start = models.DateField()
    subscription_end = models.DateField(null=True, blank=True)

    # --- Company profile -----------------------------------------
    address = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)

    # --- Tax / business registration -------------------------------
    # "PAN/VAT" is common terminology across many countries (India's
    # PAN, VAT/GST elsewhere) for a business tax ID. Kept as one
    # number field plus one uploaded proof document. If a client ever
    # needs MULTIPLE registration documents on file, that's a small
    # follow-up (a separate ClientDocument model) -- not needed yet.
    tax_registration_number = models.CharField(
        max_length=100, blank=True,
        help_text="PAN, VAT, GSTIN, or equivalent business tax registration number.",
    )
    tax_document = models.FileField(
        upload_to="client_documents/%Y/%m/", null=True, blank=True,
        help_text="Scanned registration certificate or equivalent proof document.",
    )

    # --- Primary contact --------------------------------------------
    # Who Soori's own team actually talks to for account matters --
    # distinct from any Client Admin LOGIN, which may not even exist
    # yet at the point this company is first being onboarded.
    contact_person_name = models.CharField(max_length=255, blank=True)
    contact_person_phone = models.CharField(max_length=30, blank=True)
    contact_person_email = models.EmailField(blank=True)

    # Often genuinely different from the contact person above -- many
    # companies route invoices to an accounts-payable inbox rather
    # than the person who manages the day-to-day product relationship.
    billing_email = models.EmailField(blank=True)

    # Soori's OWN private notes about running this account (e.g.
    # "renewed for 2 years", "escalation contact differs from
    # primary"). Explicitly NOT the Client's own operational data --
    # this is Soori-side account-management context, which is exactly
    # the kind of thing Soori Admin should have.
    internal_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_currently_active(self):
        """
        The single source of truth for "can this Client's own users
        actually use the product right now" -- checked live on every
        request (see IsClientSubscriptionActive in core/permissions.py),
        not something that depends on a background job flipping
        `status` at midnight. Two independent ways to be blocked:
        1. `status` explicitly set to suspended/cancelled (an admin
           action), regardless of what the dates say.
        2. `subscription_end` has actually passed, even if nobody got
           around to updating `status` yet -- the date is authoritative
           on its own, so an expired subscription can't accidentally
           keep working just because a status field wasn't touched.
        """
        if self.status in (SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED):
            return False
        if self.subscription_end is not None and self.subscription_end < timezone.now().date():
            return False
        return True

    def __str__(self):
        return self.name


class StaffPermission:
    """
    The vocabulary of things a staff role can be allowed to do.

    Deliberately a small, fixed list of CODES rather than a database
    table of permissions. Permissions are checked by name in code --
    `has_perm("tickets.assign")` only means anything because some line
    of Python actually asks that question. Letting people invent new
    permission rows at runtime would produce permissions that look
    real in the UI but are enforced nowhere, which is worse than not
    having them.

    What IS dynamic is which permissions each role holds, and what
    roles exist -- that's the part a Service Manager genuinely needs
    to change without a developer.
    """

    ASSIGN_TICKETS = "tickets.assign"
    RECEIVE_TICKETS = "tickets.receive"
    VIEW_REPORTS = "reports.view"
    MANAGE_TEAM = "team.manage"
    VIEW_AUDIT_LOG = "audit.view"
    # Service reports -- the document an engineer produces after
    # attending a site. Named distinctly from VIEW_REPORTS above, which
    # is the analytics dashboard: two different things that both got
    # called "reports" in conversation.
    WRITE_SERVICE_REPORT = "service_report.write"
    APPROVE_SERVICE_REPORT = "service_report.approve"
    # Standing access to OTHER people's service reports -- i.e. customer
    # service history. Deliberately NOT given to Field Engineers: the
    # company's stated concern is that engineers leave, so their view of
    # customer records is granted temporarily via an access code instead
    # of permanently through their login.
    VIEW_ALL_SERVICE_REPORTS = "service_report.view_all"
    # Browsing the training video collection. Also withheld from Field
    # Engineers by design -- the recordings exist to train interns, and
    # the company doesn't want the engineer who filmed them retaining a
    # browsable library of customer sites.
    VIEW_KNOWLEDGE_BASE = "knowledge_base.view"

    CHOICES = [
        (ASSIGN_TICKETS, "Assign tickets to engineers"),
        (RECEIVE_TICKETS, "Can be assigned tickets (attends site)"),
        (VIEW_REPORTS, "View reports and analytics"),
        (MANAGE_TEAM, "Add and edit team members"),
        (VIEW_AUDIT_LOG, "View the audit log"),
        (WRITE_SERVICE_REPORT, "Write service reports after attending a site"),
        (APPROVE_SERVICE_REPORT, "Review reports and release a summary to the customer"),
        (VIEW_ALL_SERVICE_REPORTS, "View service history for all customers"),
        (VIEW_KNOWLEDGE_BASE, "Browse the Knowledge Base video library"),
    ]

    ALL = [code for code, _ in CHOICES]


class StaffRole(models.Model):
    """
    A configurable job role inside ONE company's service organisation
    -- e.g. "Field Engineer", "Service Department", or something that
    company invents later like "Regional Lead".

    Scoped per-Client on purpose. Different companies structure their
    service teams differently, and a global role list would force every
    tenant into whatever the first one happened to need. It also means
    one company renaming or re-permissioning a role can't affect
    anyone else.

    NOTE this is deliberately separate from accounts.Role (soori_admin
    / client_admin / support_staff / sub_client). Those four are
    STRUCTURAL -- they decide tenancy and data isolation, and are
    fixed in code precisely because a mistake there leaks one
    company's data to another. StaffRole only ever refines what a
    support_staff member can do INSIDE their own company, so a
    misconfiguration here is a workflow problem, not a breach.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="staff_roles")
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)

    # A plain list of permission codes from StaffPermission.ALL.
    # JSONField rather than a many-to-many table: the set is small,
    # always read all-at-once, and never queried across roles -- a
    # join table would add machinery for no benefit here.
    permissions = models.JSONField(default=list, blank=True)

    # Seeded defaults every company starts with. Editable, but not
    # deletable -- deleting the only role that can receive tickets
    # would quietly break assignment with no obvious cause.
    is_system = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["client", "name"], name="unique_staff_role_name_per_client"),
        ]

    def __str__(self):
        return f"{self.name} ({self.client.name})"

    def has_perm(self, code):
        return code in (self.permissions or [])


class SupportStaffProfile(models.Model):
    """
    Role-specific data for a Support Staff user, one-to-one with User.

    Kept separate from User rather than adding `staff_role`/`department`
    directly onto User because those fields are meaningless for the
    other 3 roles -- folding them into User would mean every Soori Admin
    and Sub-Client row carries NULL staff columns forever. One-to-one
    profile tables keep User itself lean and auth-focused.
    """

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="staff_profile",
        limit_choices_to={"role": "support_staff"},
    )

    # "Keep flexible" per spec -- choices can grow without a schema
    # change. If this needs to become fully admin-configurable later
    # (client-defined tiers), swap this for a FK to a small StaffRole
    # lookup table; the rest of the system only cares that `staff_role`
    # exists as a string, so that swap is low-risk.
    # Points at a configurable StaffRole row rather than a hardcoded
    # choice, so a Service Manager can create roles their org actually
    # needs without a code change. Nullable only so the migration that
    # introduced it had somewhere to start -- in practice every staff
    # member has one (enforced by SupportStaffCreateSerializer).
    role = models.ForeignKey(
        "clients.StaffRole",
        # SET_NULL, not PROTECT. PROTECT seemed safer -- "never orphan
        # a staff member" -- but it also made deleting a whole COMPANY
        # impossible: removing the company cascades to its roles, and
        # the protection refused, so any staff member anywhere blocked
        # the entire deletion with an unreadable ProtectedError.
        #
        # Guarding against deleting an in-use ROLE belongs at the API
        # level, where it can explain itself -- see
        # StaffRoleViewSet.perform_destroy, which refuses with a clear
        # message naming how many staff still hold it. This FK just
        # needs a safe fallback for the cases that bypass the API
        # (shell, admin, company deletion).
        #
        # Failure mode if it ever does happen: role becomes None, and
        # User.has_staff_perm returns False for everything -- so the
        # person loses permissions rather than silently keeping them.
        # Losing access is recoverable; keeping it wrongly isn't.
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="staff_members",
    )

    # Which city/area this engineer covers. Matched (case-insensitively)
    # against the customer's own area so a ticket can be routed to
    # someone actually near them -- see the `nearby-engineers` action
    # on TicketViewSet.
    #
    # Plain text rather than map coordinates on purpose: real distance
    # routing needs a geocoding service, ongoing API costs, and clean
    # address data, none of which exist here yet. Matching "Kathmandu"
    # to "Kathmandu" solves the actual problem ("don't send someone
    # across the country") at a fraction of the complexity, and the
    # manager still picks the final person.
    service_area = models.CharField(
        max_length=120, blank=True,
        help_text="City or area this engineer covers, e.g. 'Kathmandu'.",
    )
    # Needed so there's somewhere to actually send an SMS notification
    # (e.g. "you've been assigned a ticket") once an SMS provider is
    # wired up. SubClientProfile already had this; Support Staff
    # didn't, purely because nothing needed it until now.
    phone = models.CharField(max_length=30, blank=True)
    department = models.CharField(max_length=100, blank=True)
    is_active_agent = models.BooleanField(default=True)

    @property
    def client(self):
        return self.user.client

    @property
    def client_id(self):
        return self.user.client_id

    def __str__(self):
        return f"{self.user.username} - {self.staff_role}"


class SubClientProfile(models.Model):
    """
    Role-specific data for a Sub-Client -- the Client's own end
    customer. A Sub-Client is itself a business (hence `company_name`
    below), so it gets the same onboarding rigor and subscription
    tracking as a Client does with Soori -- just one level down:
    Client Admin plays the "Soori Admin" role here, managing THEIR
    customer's account the same way Soori Admin manages Clients.
    """

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="sub_client_profile",
        limit_choices_to={"role": "sub_client"},
    )
    company_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    # Where this customer actually is. Matched against a Field
    # Engineer's service_area so tickets can be routed to someone
    # nearby -- the whole point of the field-engineer model is that
    # someone physically travels to the site.
    service_area = models.CharField(
        max_length=120, blank=True,
        help_text="City or area this customer is located in, e.g. 'Kathmandu'.",
    )

    # --- Company profile, mirroring Client's fields -----------------
    address = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)
    tax_registration_number = models.CharField(
        max_length=100, blank=True,
        help_text="PAN, VAT, GSTIN, or equivalent business tax registration number.",
    )
    tax_document = models.FileField(
        upload_to="subclient_documents/%Y/%m/", max_length=255, null=True, blank=True,
        help_text="Scanned registration certificate or equivalent proof document.",
    )
    contact_person_name = models.CharField(max_length=255, blank=True)
    contact_person_email = models.EmailField(blank=True)
    billing_email = models.EmailField(blank=True)
    # The CLIENT's own private notes about this Sub-Client account --
    # same idea as Client.internal_notes, just one level down (Soori's
    # notes about a Client vs. a Client's notes about their customer).
    internal_notes = models.TextField(blank=True)

    # --- Subscription, mirroring Client's fields --------------------
    # Nullable/optional at the DB level (unlike a brand-new required
    # field on Client) specifically so any Sub-Client created BEFORE
    # this feature existed doesn't break -- new Sub-Clients have this
    # required at creation time instead (see SubClientCreateSerializer).
    plan = models.CharField(max_length=20, choices=SubscriptionPlan.choices, default=SubscriptionPlan.BASIC)
    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIAL)
    subscription_period = models.CharField(
        max_length=20, choices=SubscriptionPeriod.choices, default=SubscriptionPeriod.ONE_MONTH,
    )
    subscription_start = models.DateField(null=True, blank=True)
    subscription_end = models.DateField(null=True, blank=True)

    @property
    def client(self):
        return self.user.client

    @property
    def client_id(self):
        return self.user.client_id

    def __str__(self):
        return f"{self.user.username} ({self.company_name or 'no company set'})"

