from rest_framework import exceptions, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from core.permissions import IsClientAdmin, IsClientSubscriptionActive, IsSameTenant, IsServiceLayer, IsSooriAdmin, IsSooriAdminOrServiceLayer, TenantScopedQuerySetMixin

from .models import Client, StaffRole, SubClientProfile, SupportStaffProfile
from .serializers import (
    ClientCreateSerializer,
    ClientSerializer,
    StaffRoleSerializer,
    SubClientCreateSerializer,
    SubClientSerializer,
    SupportStaffCreateSerializer,
    SupportStaffSerializer,
)


class ClientViewSet(viewsets.ModelViewSet):
    """
    Client itself IS the tenant boundary, so it doesn't use
    TenantScopedQuerySetMixin (there's no `client` field on Client to
    filter by -- we instead filter on `id` against the caller's own
    client_id). Only Soori Admin can create/update/destroy a Client;
    a Client Admin (or anyone in that org) can view their own record.
    """

    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]
    # tax_document is a file upload -- needs multipart parsing.
    # JSONParser stays too, for updates that don't touch the file.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action == "create":
            return ClientCreateSerializer
        return ClientSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsSooriAdmin()]
        # Confirmed gap: this used to allow ANY authenticated user at
        # the company to read this -- including a Field Engineer
        # calling the API directly, bypassing the frontend's own
        # subscription-card check entirely. Subscription/billing detail
        # is Service Layer information (Manager + Service Department),
        # never a Field Engineer's, and Soori Admin's own access to
        # every Client is handled separately above and untouched here.
        return [IsAuthenticated(), IsSooriAdminOrServiceLayer()]

    def get_queryset(self):
        user = self.request.user
        if user.is_soori_admin:
            return Client.objects.all()
        return Client.objects.filter(id=user.client_id)


class SupportStaffViewSet(TenantScopedQuerySetMixin, viewsets.ModelViewSet):
    """Support Staff roster for a Client, managed by that Client's admin."""

    queryset = SupportStaffProfile.objects.select_related("user", "user__client")
    serializer_class = SupportStaffSerializer
    tenant_field = "user__client"  # profile has no direct `client` FK

    def get_serializer_class(self):
        if self.action == "create":
            return SupportStaffCreateSerializer
        return SupportStaffSerializer

    def get_permissions(self):
        # NOTE: this method being overridden means the `permission_classes`
        # class attribute (if set) would never actually be read by DRF --
        # every permission has to be listed in the lists returned here.
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsClientAdmin(), IsSameTenant(), IsClientSubscriptionActive()]
        return [IsAuthenticated(), IsSameTenant(), IsClientSubscriptionActive()]

    def perform_destroy(self, instance):
        """
        Deleting the PROFILE alone used to leave the underlying User
        account fully intact and able to log in -- a removed staff
        member could still sign in and read the whole company's
        tickets (confirmed with a real test before this fix). The
        profile's FK is on_delete=CASCADE from User -> profile, which
        only cascades in that direction, not the reverse.

        soft_delete() disables the login and frees up the username and
        email for reuse, while keeping the row so ticket history that
        references this person doesn't break. See User.soft_delete().
        """
        user = instance.user
        instance.delete()
        user.soft_delete()


class SubClientViewSet(TenantScopedQuerySetMixin, viewsets.ModelViewSet):
    """A Client's own end customers."""

    queryset = SubClientProfile.objects.select_related("user", "user__client")
    serializer_class = SubClientSerializer
    tenant_field = "user__client"
    # tax_document is a file upload now (mirrors ClientViewSet) --
    # needs multipart parsing. JSONParser stays for updates that don't
    # touch the file.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action == "create":
            return SubClientCreateSerializer
        return SubClientSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsClientAdmin(), IsSameTenant(), IsClientSubscriptionActive()]
        # Even list/retrieve is restricted now -- confirmed this
        # endpoint had NO role check at all, meaning any authenticated
        # Field Engineer could browse the full customer directory
        # (address, tax registration, billing email, internal notes)
        # for every customer at the company, not just the one they're
        # assigned to visit. The engineer still gets exactly what they
        # need for their own job -- the customer's address -- directly
        # on the ticket itself (TicketSerializer.customer_address).
        # Full company records stay with whoever coordinates or
        # manages the account.
        return [IsAuthenticated(), IsSameTenant(), IsClientSubscriptionActive(), IsServiceLayer()]

    def perform_destroy(self, instance):
        """Same reasoning as SupportStaffViewSet.perform_destroy above."""
        user = instance.user
        instance.delete()
        user.soft_delete()


class StaffRoleViewSet(TenantScopedQuerySetMixin, viewsets.ModelViewSet):
    """
    Lets a Service Manager define the roles their own organisation
    actually needs, and choose what each one can do -- without a
    developer or a deployment.

    Scoped to the caller's own company throughout: the queryset mixin
    filters reads, and perform_create stamps the company on writes, so
    there's no way to see or touch another company's roles.
    """

    queryset = StaffRole.objects.all()
    serializer_class = StaffRoleSerializer
    permission_classes = [IsAuthenticated, IsClientSubscriptionActive]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsClientAdmin(), IsClientSubscriptionActive()]
        return [IsAuthenticated(), IsClientSubscriptionActive()]

    def perform_create(self, serializer):
        serializer.save(client=self.request.user.client)

    def perform_destroy(self, instance):
        # Two guards, both protecting against silent breakage:
        # a system role is what the company falls back on, and a role
        # still in use would orphan those staff members (the FK is
        # PROTECT, so the database would refuse anyway -- this just
        # turns that into a readable message instead of a 500).
        if instance.is_system:
            raise exceptions.ValidationError(
                "Built-in roles can't be deleted. You can rename one or change its permissions instead."
            )
        if instance.staff_members.exists():
            count = instance.staff_members.count()
            raise exceptions.ValidationError(
                f"{count} staff member(s) still have this role. Move them to another role first."
            )
        instance.delete()
