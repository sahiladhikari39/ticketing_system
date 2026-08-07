from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import Role, User
from accounts.provisioning import generate_temporary_password, send_credentials_email

from .models import (
    PERIOD_TO_MONTHS,
    Client,
    StaffPermission,
    StaffRole,
    SubClientProfile,
    SubscriptionPeriod,
    SubscriptionPlan,
    SupportStaffProfile,
)


def compute_subscription_end(start_date, period):
    """
    Calendar-correct month arithmetic via dateutil's relativedelta --
    NOT `start_date + timedelta(days=30*months)`. A plain day-count
    approximation drifts (12 "months" of 30 days is 360 days, not a
    year) and mishandles month-end edge cases (Jan 31 + 1 month should
    land on Feb 28, not March 2 or 3).
    """
    months = PERIOD_TO_MONTHS.get(period)
    if not months or not start_date:
        return None
    return start_date + relativedelta(months=months)


class ClientSerializer(serializers.ModelSerializer):
    # Computed, not stored -- always "as of right now" rather than a
    # stale number that would need a background job to keep current.
    days_remaining = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id", "name", "plan", "status",
            "subscription_period", "subscription_start", "subscription_end", "days_remaining",
            "address", "country",
            "tax_registration_number", "tax_document",
            "contact_person_name", "contact_person_phone", "contact_person_email",
            "billing_email", "internal_notes",
            "created_at",
        ]
        # subscription_end is DERIVED from subscription_period +
        # subscription_start (see compute_subscription_end above) --
        # never something to type in directly. Still fully visible in
        # every response, just not writable.
        read_only_fields = ["id", "subscription_end", "days_remaining", "created_at"]

    def get_days_remaining(self, obj):
        if not obj.subscription_end:
            return None
        return (obj.subscription_end - timezone.now().date()).days

    def update(self, instance, validated_data):
        # Recompute subscription_end whenever period or start actually
        # changes (e.g. renewing for another term) -- this is what lets
        # Soori Admin renew a subscription by picking a period rather
        # than calculating a date by hand.
        if "subscription_period" in validated_data or "subscription_start" in validated_data:
            period = validated_data.get("subscription_period", instance.subscription_period)
            start = validated_data.get("subscription_start", instance.subscription_start)
            validated_data["subscription_end"] = compute_subscription_end(start, period)
        return super().update(instance, validated_data)


class ClientCreateSerializer(serializers.ModelSerializer):
    """
    Used ONLY for the `create` action (see ClientViewSet.get_serializer_class).
    This is the fix for the missing registration flow: creating a
    Client now also provisions its first Client Admin login in the
    same request -- a generated password, emailed to them, never
    returned in the API response itself.
    """

    admin_username = serializers.CharField(write_only=True)
    admin_email = serializers.EmailField(write_only=True)
    # Required here even though the model field itself stays
    # null=True/blank=True (see Client.tax_document) -- enforcing it at
    # creation only, not at the DB level, means: (1) it doesn't break
    # any existing client records that predate this rule, and (2) a
    # later PATCH that only changes an unrelated field (like a phone
    # number) is never forced to also include a file it isn't touching.
    tax_document = serializers.FileField(required=True)

    class Meta:
        model = Client
        fields = [
            "id", "name", "plan", "subscription_period", "subscription_start",
            "address", "country",
            "tax_registration_number", "tax_document",
            "contact_person_name", "contact_person_phone", "contact_person_email",
            "billing_email", "internal_notes",
            "admin_username", "admin_email",
        ]
        read_only_fields = ["id"]
        # subscription_end deliberately isn't a field here at all --
        # it's computed from period + start below, in create().

    def validate_admin_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate_admin_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("That email is already in use.")
        return value

    def create(self, validated_data):
        admin_username = validated_data.pop("admin_username")
        admin_email = validated_data.pop("admin_email")
        request = self.context.get("request")

        period = validated_data.get("subscription_period", SubscriptionPeriod.ONE_MONTH)
        validated_data["subscription_end"] = compute_subscription_end(
            validated_data.get("subscription_start"), period
        )

        # Client + its first Client Admin user are created together, in
        # one transaction -- if anything fails partway (e.g. the User
        # save), the Client row doesn't get left behind as an orphan
        # with nobody able to log in and manage it.
        with transaction.atomic():
            client = Client.objects.create(
                registered_by=request.user if request else None,
                **validated_data,
            )
            # Seed the default roles immediately. Without these a new
            # Service Manager logs in to find they can't add a single
            # staff member, because there'd be no role to assign them.
            # Editable and extendable afterwards -- just a starting point.
            StaffRole.objects.create(
                client=client, name="Service Department", is_system=True,
                description="Coordinates incoming tickets and assigns Field Engineers.",
                permissions=[
                    StaffPermission.ASSIGN_TICKETS,
                    StaffPermission.VIEW_REPORTS,
                    StaffPermission.APPROVE_SERVICE_REPORT,
                    StaffPermission.VIEW_ALL_SERVICE_REPORTS,
                    StaffPermission.VIEW_KNOWLEDGE_BASE,
                ],
            )
            StaffRole.objects.create(
                client=client, name="Field Engineer", is_system=True,
                description="Attends the customer site and resolves the ticket.",
                permissions=[
                    StaffPermission.RECEIVE_TICKETS,
                    StaffPermission.VIEW_REPORTS,
                    StaffPermission.WRITE_SERVICE_REPORT,
                ],
            )
            password = generate_temporary_password()
            admin_user = User.objects.create_user(
                username=admin_username,
                email=admin_email,
                password=password,
                role=Role.CLIENT_ADMIN,
                client=client,
            )

        send_credentials_email(admin_user, password, "Client Admin", client.name)
        return client

    def to_representation(self, instance):
        # Represent the created Client using the normal read serializer
        # -- the admin_username/admin_email write-only fields were only
        # ever meant as input, never echoed back in the response.
        return ClientSerializer(instance, context=self.context).data


class StaffRoleSerializer(serializers.ModelSerializer):
    staff_count = serializers.SerializerMethodField()
    available_permissions = serializers.SerializerMethodField()

    class Meta:
        model = StaffRole
        fields = [
            "id", "name", "description", "permissions",
            "is_system", "staff_count", "available_permissions",
        ]
        # client is set from the request, never the payload -- same
        # reasoning as every other tenant-scoped write here.
        read_only_fields = ["id", "is_system", "staff_count", "available_permissions"]

    def get_staff_count(self, obj):
        return obj.staff_members.count()

    def get_available_permissions(self, obj):
        """
        Ships the full vocabulary with every response so the frontend
        can render checkboxes without hardcoding the list separately
        and drifting out of sync with the backend.
        """
        return [{"code": code, "label": label} for code, label in StaffPermission.CHOICES]

    def validate_permissions(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Permissions must be a list of permission codes.")
        unknown = [p for p in value if p not in StaffPermission.ALL]
        if unknown:
            raise serializers.ValidationError(
                f"Unknown permission code(s): {', '.join(unknown)}. "
                f"Valid codes are: {', '.join(StaffPermission.ALL)}."
            )
        return value


class SupportStaffSerializer(serializers.ModelSerializer):
    # Pull a couple of read-friendly fields off the related User so the
    # frontend doesn't need a second request just to show a name/email.
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.SerializerMethodField()
    role_name = serializers.CharField(source="role.name", read_only=True, default="")
    role_permissions = serializers.JSONField(source="role.permissions", read_only=True, default=list)

    class Meta:
        model = SupportStaffProfile
        fields = [
            "user", "username", "email", "full_name",
            "role", "role_name", "role_permissions",
            "department", "phone", "service_area", "is_active_agent",
        ]
        read_only_fields = ["user"]

    def get_full_name(self, obj):
        return obj.user.get_full_name()


class SupportStaffCreateSerializer(serializers.Serializer):
    """
    Used ONLY for `create` (see SupportStaffViewSet.get_serializer_class).
    Not a ModelSerializer -- username/email belong to User, not
    SupportStaffProfile, so there's no single model to bind Meta.fields
    to here. Creates both together, atomically, same pattern as
    ClientCreateSerializer above.
    """

    username = serializers.CharField()
    email = serializers.EmailField()
    # A StaffRole ID, not a fixed choice -- validated below against
    # the creating manager's OWN company, so one company can never
    # attach its staff to another company's role.
    role = serializers.UUIDField()
    service_area = serializers.CharField(required=False, allow_blank=True, default="")
    department = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("That email is already in use.")
        return value

    def validate_role(self, value):
        request = self.context["request"]
        role = StaffRole.objects.filter(id=value, client=request.user.client).first()
        if role is None:
            raise serializers.ValidationError("That role doesn't exist in your organisation.")
        return role

    def create(self, validated_data):
        request = self.context["request"]
        # The new hire's tenant is always the CREATING Client Admin's
        # own client -- never something the request body could
        # override, same reasoning as every other tenant-scoped write
        # in this project.
        client = request.user.client

        with transaction.atomic():
            password = generate_temporary_password()
            user = User.objects.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=password,
                role=Role.SUPPORT_STAFF,
                client=client,
            )
            profile = SupportStaffProfile.objects.create(
                user=user,
                role=validated_data["role"],
                department=validated_data.get("department", ""),
                phone=validated_data.get("phone", ""),
                service_area=validated_data.get("service_area", ""),
            )

        send_credentials_email(user, password, "Support Staff member", client.name)
        return profile

    def to_representation(self, instance):
        return SupportStaffSerializer(instance, context=self.context).data


class SubClientSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    # Computed, not stored -- same pattern as ClientSerializer.days_remaining
    # above: always "as of right now" rather than a number that would
    # need a background job to keep current.
    days_remaining = serializers.SerializerMethodField()

    class Meta:
        model = SubClientProfile
        fields = [
            "user", "username", "email", "company_name", "phone", "service_area",
            "address", "country",
            "tax_registration_number", "tax_document",
            "contact_person_name", "contact_person_email",
            "billing_email", "internal_notes",
            "plan", "status", "subscription_period",
            "subscription_start", "subscription_end", "days_remaining",
        ]
        # subscription_end is derived from subscription_period +
        # subscription_start -- same reasoning as Client, never typed
        # in directly.
        read_only_fields = ["user", "subscription_end", "days_remaining"]

    def get_days_remaining(self, obj):
        if not obj.subscription_end:
            return None
        return (obj.subscription_end - timezone.now().date()).days

    def update(self, instance, validated_data):
        if "subscription_period" in validated_data or "subscription_start" in validated_data:
            period = validated_data.get("subscription_period", instance.subscription_period)
            start = validated_data.get("subscription_start", instance.subscription_start)
            validated_data["subscription_end"] = compute_subscription_end(start, period)
        return super().update(instance, validated_data)


class SubClientCreateSerializer(serializers.Serializer):
    """
    Used ONLY for `create`. Mirrors ClientCreateSerializer's fields and
    reasoning almost exactly -- a Sub-Client is registered with the
    same rigor a Client is, one level down (Client Admin doing the
    registering here, instead of Soori Admin).
    """

    username = serializers.CharField()
    email = serializers.EmailField()
    company_name = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    service_area = serializers.CharField(required=False, allow_blank=True, default="")

    address = serializers.CharField(required=False, allow_blank=True, default="")
    country = serializers.CharField(required=False, allow_blank=True, default="")
    tax_registration_number = serializers.CharField(required=False, allow_blank=True, default="")
    # Required here even though the model field stays null=True/blank=True
    # -- same reasoning as Client.tax_document: enforced at creation
    # only, so it doesn't break existing rows or force a re-upload on
    # every unrelated edit later.
    tax_document = serializers.FileField(required=True)
    contact_person_name = serializers.CharField(required=False, allow_blank=True, default="")
    contact_person_email = serializers.EmailField(required=False, allow_blank=True, default="")
    billing_email = serializers.EmailField(required=False, allow_blank=True, default="")
    internal_notes = serializers.CharField(required=False, allow_blank=True, default="")

    plan = serializers.ChoiceField(choices=SubscriptionPlan.choices, default=SubscriptionPlan.BASIC)
    subscription_period = serializers.ChoiceField(choices=SubscriptionPeriod.choices, default=SubscriptionPeriod.ONE_MONTH)
    subscription_start = serializers.DateField(required=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("That email is already in use.")
        return value

    def create(self, validated_data):
        request = self.context["request"]
        client = request.user.client

        subscription_end = compute_subscription_end(
            validated_data["subscription_start"], validated_data.get("subscription_period", SubscriptionPeriod.ONE_MONTH)
        )

        with transaction.atomic():
            password = generate_temporary_password()
            user = User.objects.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=password,
                role=Role.SUB_CLIENT,
                client=client,
            )
            profile = SubClientProfile.objects.create(
                user=user,
                company_name=validated_data.get("company_name", ""),
                phone=validated_data.get("phone", ""),
                service_area=validated_data.get("service_area", ""),
                address=validated_data.get("address", ""),
                country=validated_data.get("country", ""),
                tax_registration_number=validated_data.get("tax_registration_number", ""),
                tax_document=validated_data.get("tax_document"),
                contact_person_name=validated_data.get("contact_person_name", ""),
                contact_person_email=validated_data.get("contact_person_email", ""),
                billing_email=validated_data.get("billing_email", ""),
                internal_notes=validated_data.get("internal_notes", ""),
                plan=validated_data.get("plan", SubscriptionPlan.BASIC),
                subscription_period=validated_data.get("subscription_period", SubscriptionPeriod.ONE_MONTH),
                subscription_start=validated_data["subscription_start"],
                subscription_end=subscription_end,
            )

        send_credentials_email(user, password, "Sub-Client", client.name)
        return profile

    def to_representation(self, instance):
        return SubClientSerializer(instance, context=self.context).data
