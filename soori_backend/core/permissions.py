"""
Shared, reusable pieces for tenant scoping and role-based permissions.
Import these into every app's views.py rather than reimplementing
tenant filtering per app.
"""

from rest_framework import permissions


class TenantScopedQuerySetMixin:
    """
    Mix into any ModelViewSet whose model (or a FK chain from it) has a
    `client` field. Centralizes the "who can see whose rows" decision so
    it isn't re-derived (and potentially gotten wrong) in every view.

    Decision rule: every viewset using this mixin is scoped strictly to
    request.user.client_id -- INCLUDING Soori Admin. Soori Admin runs
    the platform (billing, subscriptions, onboarding new Clients) --
    they should never see a Client's own operational data: their
    tickets, ticket conversations, support staff roster, sub-client
    roster, or audit trail. That's the Client's own business, the same
    way a cloud provider doesn't get to read what's inside your
    storage buckets just because they run the platform underneath it.

    Soori Admin's cross-tenant visibility exists ONLY on the Client
    model itself (see ClientViewSet.get_queryset, which is deliberately
    NOT built on this mixin) -- company profile, billing, and
    subscription details, never the Client's own product usage.

    Since Soori Admin's client_id is None by design (enforced by a DB
    constraint on User), they fall straight into the "no client ->
    return nothing" branch below with no special case needed.

    Why a request-scoped viewset mixin, and NOT a custom manager that
    "automatically" filters every query for the model?
    A manager-level default sounds convenient but has no access to
    `request.user` -- to make it automatic you'd have to smuggle the
    current user into thread-local/global state (via middleware), which
    is a well-known Django anti-pattern: it silently changes what a
    queryset returns depending on invisible ambient context, breaks in
    Celery tasks/management commands/tests/shell, and makes it very easy
    to accidentally query "everything" or "nothing" without noticing.
    A viewset mixin keeps scoping explicit and tied to an actual
    request/user pair you can trace and unit test.

    Trade-off you accept: you must remember to add this mixin (or do
    equivalent manual filtering) on every viewset that touches a
    tenant-scoped model. Treat that as a checklist item, and write a
    test per viewset asserting that a user from Client A never sees a
    row belonging to Client B, regardless of query params or ordering.
    """

    # Override per-viewset when the FK to Client isn't literally called
    # `client` on the model being queried, or when it's a hop away
    # (e.g. TicketComment doesn't have `client` -- it has
    # `ticket.client`, so tenant_field = "ticket__client").
    tenant_field = "client"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if not user.is_authenticated:
            return qs.none()

        if user.client_id is None:
            # Covers Soori Admin (no client, by design -- see class
            # docstring) and the "should never happen" case of anyone
            # else missing a client. Either way, never fall back to
            # returning everything.
            return qs.none()

        return qs.filter(**{self.tenant_field: user.client_id})


class IsSooriAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_soori_admin)


class IsClientAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_client_admin)


class IsSupportStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_support_staff)


class IsSubClient(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_sub_client)


class IsSameTenant(permissions.BasePermission):
    """
    Object-level guard, meant as DEFENSE IN DEPTH on top of
    TenantScopedQuerySetMixin -- not a replacement for it.

    The queryset mixin should already make it impossible to fetch
    another tenant's row via list/retrieve. This permission catches the
    case where that queryset filtering was forgotten on a particular
    viewset, or a nested/custom route bypasses `get_queryset` entirely
    (e.g. a lookup by PK against `Model.objects.all()` in a custom
    action). Cheap to include, so include it everywhere.

    No Soori Admin bypass here (deliberately) -- see
    TenantScopedQuerySetMixin's docstring for why Soori Admin doesn't
    get cross-tenant access to a Client's own operational data at all.
    """

    tenant_field = "client_id"

    def has_object_permission(self, request, view, obj):
        user = request.user
        obj_client_id = getattr(obj, self.tenant_field, None)
        return obj_client_id is not None and obj_client_id == user.client_id


class IsClientSubscriptionActive(permissions.BasePermission):
    """
    Blocks a Client's own users (Client Admin, Support Staff,
    Sub-Client) from using ticket-related endpoints once that Client's
    subscription has lapsed -- expired by date, or explicitly
    suspended/cancelled. See Client.is_currently_active for exactly
    what "lapsed" means.

    Deliberately NOT applied to ClientViewSet -- a Client Admin needs
    to still be able to see their OWN subscription status (via
    GET /api/clients/) precisely BECAUSE it's expired, so they know to
    renew. Blocking that view too would hide the exact information
    someone needs to fix the problem.

    Deliberately skips Soori Admin entirely -- they need full access
    to a Client's record regardless of that Client's own subscription
    state, since renewing an expired subscription is literally their
    job. This permission is about restricting the Client's OWN users,
    never the platform owner.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or user.is_soori_admin:
            return True
        if user.client is None or user.client.is_currently_active:
            return True

        # Message tailored per role -- a Sub-Client can't renew
        # anything themselves, so telling them "contact your admin"
        # (their own company) is more useful than mentioning billing
        # they have no ability to act on. `self.code` is picked up by
        # DRF's permission_denied() and surfaced in the response body
        # by core/exception_handlers.py, so the frontend can detect
        # this exact scenario instead of guessing from message text.
        self.code = "subscription_inactive"
        if user.role == "client_admin":
            self.message = "Your organization's Soori subscription has expired. Please renew to continue."
        elif user.role == "support_staff":
            self.message = "Your organization's Soori subscription has expired. Contact your Client Admin to renew."
        else:
            self.message = "This support portal is temporarily unavailable. Please contact the company directly."
        return False


class HasStaffPermission(permissions.BasePermission):
    """
    Generic permission class backed by the dynamic StaffRole system.

    Subclass it and set `required_permission`, rather than writing a
    new hardcoded IsSomeRole class each time -- the whole point of
    dynamic roles is that new roles shouldn't require new code.
    """

    required_permission = None

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or self.required_permission is None:
            return False
        return user.has_staff_perm(self.required_permission)


class CanViewAuditLog(HasStaffPermission):
    from clients.models import StaffPermission as _P

    required_permission = _P.VIEW_AUDIT_LOG
    message = "Your role doesn't have permission to view the audit log."


class CanManageTeam(HasStaffPermission):
    from clients.models import StaffPermission as _P

    required_permission = _P.MANAGE_TEAM
    message = "Your role doesn't have permission to manage team members."


class IsServiceLayer(permissions.BasePermission):
    """
    Client Admin (Service Manager) or anyone whose role can approve
    service reports (Service Department) -- i.e. the people who
    coordinate and manage the account, as opposed to a Field Engineer
    who attends individual jobs.

    Built specifically to close a real gap: a customer's full company
    record (address, tax registration, billing email, internal notes)
    was reachable by ANY authenticated staff member, including Field
    Engineers, who have no business browsing the whole customer
    directory -- they get exactly what they need for their own
    assigned job directly on the ticket instead.
    """

    message = "This is restricted to the Service Manager or Service Department."

    def has_permission(self, request, view):
        from clients.models import StaffPermission

        user = request.user
        if not user.is_authenticated:
            return False
        return user.role == "client_admin" or user.has_staff_perm(StaffPermission.APPROVE_SERVICE_REPORT)


class IsSooriAdminOrServiceLayer(permissions.BasePermission):
    """
    Soori Admin (manages every Client's subscription -- that's their
    entire job) OR the Service Layer at one's own company (Manager /
    Service Department, who need to see their own subscription status).
    A Field Engineer is neither.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_soori_admin:
            return True
        return IsServiceLayer().has_permission(request, view)
