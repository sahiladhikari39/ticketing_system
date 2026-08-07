from rest_framework import serializers

from clients.models import StaffPermission

from .models import ServiceReport, Ticket, TicketComment, TicketStatusHistory


class TicketCommentSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    attachment_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()

    # Two separate caps for two separate fields. Video gets far more
    # room because even a few seconds of screen recording dwarfs a
    # screenshot or PDF -- while holding documents to the smaller
    # limit stops someone parking a 5MB "document" on the server.
    MAX_VIDEO_SIZE_BYTES = 5 * 1024 * 1024   # 5MB
    MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024    # 2MB

    # Checked against the file's actual EXTENSION, not the
    # browser-reported content type -- content_type comes from the
    # client and can be trivially spoofed to sneak a 5MB .exe through
    # the video field's larger allowance.
    VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v")

    class Meta:
        model = TicketComment
        fields = [
            "id", "ticket", "author", "author_username", "body",
            "attachment", "attachment_url", "attachment_filename",
            "video", "video_url", "video_filename",
            "is_internal_note", "created_at",
        ]
        read_only_fields = [
            "id", "author", "attachment_filename", "video_filename", "created_at",
        ]
        extra_kwargs = {
            # Only `body` is required. BOTH uploads are optional and
            # independent -- a message can have neither, either, or both.
            "attachment": {"required": False, "allow_null": True, "write_only": True},
            "video": {"required": False, "allow_null": True, "write_only": True},
        }

    def get_attachment_url(self, obj):
        request = self.context.get("request")
        if not obj.attachment:
            return None
        return request.build_absolute_uri(obj.attachment.url) if request else obj.attachment.url

    def get_video_url(self, obj):
        request = self.context.get("request")
        if not obj.video:
            return None
        return request.build_absolute_uri(obj.video.url) if request else obj.video.url

    def validate_attachment(self, value):
        """The general-purpose file slot: documents, screenshots, logs."""
        if value is None:
            return value
        if value.size > self.MAX_FILE_SIZE_BYTES:
            actual_mb = round(value.size / (1024 * 1024), 1)
            raise serializers.ValidationError(
                f"Files must be under 2MB (this one is {actual_mb}MB). "
                f"If this is a video, use the video upload instead."
            )
        return value

    def validate_video(self, value):
        """
        The video slot specifically. Two checks, not one: it has to
        actually BE a video, and it has to fit the video limit.
        Without the extension check, this field would just be a
        general-purpose 5MB upload -- an easy way to bypass the 2MB
        file cap by putting any document here instead.
        """
        if value is None:
            return value

        filename = (value.name or "").lower()
        if not filename.endswith(self.VIDEO_EXTENSIONS):
            allowed = ", ".join(self.VIDEO_EXTENSIONS)
            raise serializers.ValidationError(
                f"This field only accepts video files ({allowed}). "
                f"Use the file upload for anything else."
            )

        if value.size > self.MAX_VIDEO_SIZE_BYTES:
            actual_mb = round(value.size / (1024 * 1024), 1)
            raise serializers.ValidationError(
                f"Videos must be under 5MB (this one is {actual_mb}MB)."
            )
        return value

    def validate_ticket(self, ticket):
        """
        Two checks here, not one:
        1. Tenant match -- prevents Company A writing onto Company B's
           ticket (the original cross-tenant fix).
        2. For a Sub-Client SPECIFICALLY, ownership match too -- without
           this, Sub-Client 1 could post a comment directly onto
           Sub-Client 2's ticket as long as they're at the SAME company,
           since tenant match alone doesn't imply same-ticket ownership.
           Confirmed this was possible before this check existed.
        """
        request = self.context.get("request")
        user = request.user if request else None
        if user is not None and not user.is_soori_admin:
            if ticket.client_id != user.client_id:
                raise serializers.ValidationError("You do not have access to this ticket.")
            if user.role == "sub_client" and ticket.created_by_id != user.id:
                raise serializers.ValidationError("You do not have access to this ticket.")
        return ticket

    def create(self, validated_data):
        attachment = validated_data.get("attachment")
        if attachment is not None:
            validated_data["attachment_filename"] = attachment.name
        video = validated_data.get("video")
        if video is not None:
            validated_data["video_filename"] = video.name
        return super().create(validated_data)


class TicketStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_username = serializers.CharField(source="changed_by.username", read_only=True, default=None)

    class Meta:
        model = TicketStatusHistory
        fields = ["id", "ticket", "from_status", "to_status", "changed_by", "changed_by_username", "changed_at"]
        # Never created directly through the API -- written automatically
        # by TicketViewSet.perform_update whenever status actually changes.
        read_only_fields = fields


class TicketSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    # The company the SUB-CLIENT belongs to -- i.e. which of this
    # Client's own customers raised the ticket. That's what a Client
    # Admin actually needs in a list view; `client_name` above is the
    # Client's OWN name, which is identical on every row they can see
    # and therefore tells them nothing.
    created_by_company = serializers.SerializerMethodField()
    # Where the customer actually is -- the whole reason a Field
    # Engineer is dispatched at all is to physically go there.
    # Existed on the customer's own profile already, but was never
    # surfaced on the ticket itself, so an assigned engineer had no
    # way to see it without a separate lookup they had no access to.
    customer_address = serializers.SerializerMethodField()
    customer_service_area = serializers.SerializerMethodField()
    assigned_to_username = serializers.CharField(source="assigned_to.username", read_only=True, default=None)
    # Changed from a plain nested serializer to a SerializerMethodField.
    # A plain `TicketCommentSerializer(many=True, read_only=True)` reads
    # straight off `ticket.comments.all()` -- it has NO knowledge of
    # TicketCommentViewSet's own get_queryset() filtering, so it would
    # leak internal-only notes (and now their attachments too) to a
    # Sub-Client fetching a ticket directly (rather than through
    # /api/ticket-comments/ itself). This does the same
    # is_internal_note filtering by hand, using the request available
    # via serializer context.
    comments = serializers.SerializerMethodField()
    status_history = TicketStatusHistorySerializer(many=True, read_only=True)
    attachment_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    # Lets the customer's ticket list show a "service report" column
    # without fetching every report separately.
    service_report_shared = serializers.SerializerMethodField()

    MAX_FILE = 2 * 1024 * 1024
    MAX_VIDEO = 5 * 1024 * 1024
    VIDEO_EXT = (".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v")

    class Meta:
        model = Ticket
        fields = [
            "id", "client", "client_name", "title", "description", "product_or_service",
            "status", "priority", "created_by", "created_by_username", "created_by_company",
            "customer_address", "customer_service_area",
            "assigned_to", "assigned_to_username",
            "created_at", "updated_at", "resolved_at",
            "attachment", "attachment_url", "attachment_filename",
            "video", "video_url", "video_filename", "service_report_shared",
            "comments", "status_history",
        ]
        # `client` and `created_by` are set server-side from the
        # requesting user in perform_create -- never trust these from
        # the client payload, or a malicious/buggy frontend could
        # create a ticket under another tenant. `resolved_at` is set
        # automatically by TicketViewSet.perform_update based on the
        # status transition, never accepted as direct input.
        read_only_fields = [
            "id", "client", "created_by", "created_at", "updated_at", "resolved_at",
            "attachment_filename", "video_filename", "service_report_shared",
        ]
        extra_kwargs = {
            "attachment": {"required": False, "allow_null": True, "write_only": True},
            "video": {"required": False, "allow_null": True, "write_only": True},
        }

    def get_attachment_url(self, obj):
        r = self.context.get("request")
        if not obj.attachment:
            return None
        return r.build_absolute_uri(obj.attachment.url) if r else obj.attachment.url

    def get_video_url(self, obj):
        r = self.context.get("request")
        if not obj.video:
            return None
        return r.build_absolute_uri(obj.video.url) if r else obj.video.url

    def get_service_report_shared(self, obj):
        report = getattr(obj, "service_report", None)
        return bool(report and report.shared_with_customer_at)

    def validate_attachment(self, value):
        if value is None:
            return value
        if value.size > self.MAX_FILE:
            mb = round(value.size / (1024 * 1024), 1)
            raise serializers.ValidationError(f"Files must be under 2MB (this one is {mb}MB).")
        return value

    def validate_video(self, value):
        if value is None:
            return value
        if not (value.name or "").lower().endswith(self.VIDEO_EXT):
            raise serializers.ValidationError("That doesn't look like a video file.")
        if value.size > self.MAX_VIDEO:
            mb = round(value.size / (1024 * 1024), 1)
            raise serializers.ValidationError(f"Videos must be under 5MB (this one is {mb}MB).")
        return value

    def get_created_by_company(self, ticket):
        """
        Falls back to the username when the raiser has no company name
        recorded -- better to show *something* identifying than a blank
        cell. Uses getattr rather than a direct attribute access
        because Support Staff and Client Admins can raise tickets too,
        and they have no sub_client_profile at all.
        """
        profile = getattr(ticket.created_by, "sub_client_profile", None)
        company = getattr(profile, "company_name", "") if profile else ""
        return company or ticket.created_by.username

    def get_customer_address(self, ticket):
        profile = getattr(ticket.created_by, "sub_client_profile", None)
        return getattr(profile, "address", "") if profile else ""

    def get_customer_service_area(self, ticket):
        profile = getattr(ticket.created_by, "sub_client_profile", None)
        return getattr(profile, "service_area", "") if profile else ""

    def validate_assigned_to(self, assignee):
        """
        Three checks, each closing a real hole:

        1. Must be Support Staff. Without this, ANY authenticated user
           could set assigned_to to any user ID in the system.
        2. Must be a FIELD ENGINEER specifically. Field engineers are
           the ones who physically go out and fix the problem --
           assigning a ticket to a Service Department coordinator would
           mean nobody is actually going to the site.
        3. Must belong to the same company as the ticket. Confirmed
           possible to violate before this existed: a
           PrimaryKeyRelatedField has no concept of tenants on its own.
        """
        if assignee is None:
            return assignee
        request = self.context.get("request")
        user = request.user if request else None
        ticket_client_id = self.instance.client_id if self.instance else (user.client_id if user else None)

        if assignee.role != "support_staff":
            raise serializers.ValidationError("Tickets can only be assigned to a Field Engineer.")

        # Checks the PERMISSION, not a hardcoded role name -- so a
        # company that invents its own role (say "Senior Engineer")
        # and grants it tickets.receive works immediately, with no
        # code change here.
        if not assignee.has_staff_perm(StaffPermission.RECEIVE_TICKETS):
            raise serializers.ValidationError(
                "Tickets can only be assigned to someone whose role can receive them "
                "(a Field Engineer, or any role granted that permission)."
            )

        if user is not None and not user.is_soori_admin and assignee.client_id != ticket_client_id:
            raise serializers.ValidationError("Can only assign to a Field Engineer at the same company.")
        return assignee

    def validate(self, attrs):
        """
        Two different permission levels here, deliberately not one:

        `status` -- any staff member can change it. An agent actively
        working a ticket has to be able to mark it in-progress or
        resolved; needing a manager for that would make the tool
        unusable day to day.

        `assigned_to` -- restricted to a Client Admin or a Support
        Staff member whose tier is 'supervisor'. Deciding WHO handles
        a ticket is a workload/ownership decision, not part of doing
        the work. Left open, any junior agent could reassign their
        queue onto a colleague, or pull someone else's ticket to
        themselves, with nothing recording that as unusual.

        Both checks read self.initial_data (the raw incoming keys)
        rather than attrs, so an attempt is caught even if the value
        itself would have failed field validation anyway.
        """
        request = self.context.get("request")
        user = request.user if request else None
        if user is None:
            return attrs

        incoming = set(self.initial_data.keys())

        # Sub-Clients: neither field, ever.
        if user.role == "sub_client":
            locked = {"status", "assigned_to"} & incoming
            if locked:
                raise serializers.ValidationError(
                    {f: "Only Support Staff or a Client Admin can change this." for f in locked}
                )
            return attrs

        # Deciding WHO attends a ticket is the coordination job, and
        # belongs to the Service Manager or their Service Department.
        # A Field Engineer must not be able to hand their own jobs to
        # a colleague, or pull someone else's onto themselves.
        if "assigned_to" in incoming:
            if not user.has_staff_perm(StaffPermission.ASSIGN_TICKETS):
                raise serializers.ValidationError({
                    "assigned_to": "Your role doesn't have permission to assign tickets."
                })

        return attrs

    def create(self, validated_data):
        for field in ("attachment", "video"):
            f = validated_data.get(field)
            if f is not None:
                validated_data[f"{field}_filename"] = f.name
        return super().create(validated_data)

    def get_comments(self, ticket):
        qs = ticket.comments.all()
        request = self.context.get("request")
        if request is not None and getattr(request.user, "role", None) == "sub_client":
            qs = qs.filter(is_internal_note=False)
        return TicketCommentSerializer(qs, many=True, context=self.context).data


class ServiceReportSerializer(serializers.ModelSerializer):
    """
    ONE serializer for both audiences, with the customer-facing cut
    applied in to_representation.

    Deliberately not two separate serializer classes: the risk with
    that approach is a new field getting added to the internal one and
    silently appearing in the customer one too (or a developer picking
    the wrong class in a new view). Here there is exactly one place
    that decides what a customer sees, and it works by REMOVING
    fields from a known list -- so a newly added internal field is
    exposed only if someone explicitly chooses to expose it.
    """

    engineer_username = serializers.CharField(source="engineer.username", read_only=True, default=None)
    summarised_by_username = serializers.CharField(source="summarised_by.username", read_only=True, default=None)
    service_video_url = serializers.SerializerMethodField()
    is_shared_with_customer = serializers.BooleanField(read_only=True)

    # This is the ENGINEER's on-site recording (an Insta360-style camera,
    # up to roughly an hour long) -- a completely different thing from
    # the customer's short evidence clip at ticket creation (capped at
    # 5MB / 10 seconds elsewhere in this file). A genuine hour of video
    # can be several GB depending on compression, so this ceiling is a
    # generous backstop against pathological uploads, not a real
    # duration limit -- the actual "keep it to about an hour" check is
    # enforced client-side (see utils/video.js on the frontend), the
    # same way the 10-second ticket-video check is. This number is a
    # reasonable assumption for a compressed training recording; if
    # real Insta360 exports run larger, this is the one place to raise.
    MAX_VIDEO_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2GB
    VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v")

    # Everything a customer is allowed to receive. Anything not on this
    # list is stripped for them -- an allow-list, not a deny-list, so
    # the failure mode of forgetting to update it is "customer sees
    # less than intended" rather than "customer sees internal notes".
    CUSTOMER_VISIBLE_FIELDS = {
        "id", "ticket", "customer_summary", "shared_with_customer_at",
        "is_shared_with_customer", "created_at",
    }

    class Meta:
        model = ServiceReport
        fields = [
            "id", "ticket", "engineer", "engineer_username",
            "work_performed", "root_cause", "parts_used", "internal_notes",
            "service_video", "service_video_url", "service_video_filename", "video_title",
            "customer_summary", "summarised_by", "summarised_by_username",
            "shared_with_customer_at", "is_shared_with_customer",
            "include_in_knowledge_base", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "engineer", "service_video_filename", "summarised_by",
            "shared_with_customer_at", "created_at", "updated_at",
        ]
        extra_kwargs = {"service_video": {"required": False, "allow_null": True, "write_only": True}}

    def get_service_video_url(self, obj):
        request = self.context.get("request")
        if not obj.service_video:
            return None
        return request.build_absolute_uri(obj.service_video.url) if request else obj.service_video.url

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = request.user if request else None

        if user is not None and getattr(user, "role", None) == "sub_client":
            # Not yet released? The customer gets nothing at all, not
            # an empty shell that hints a report exists.
            if not instance.is_shared_with_customer:
                return {"detail": "No report has been shared for this ticket yet."}
            return {k: v for k, v in data.items() if k in self.CUSTOMER_VISIBLE_FIELDS}

        return data

    def validate_service_video(self, value):
        if value is None:
            return value
        filename = (value.name or "").lower()
        if not filename.endswith(self.VIDEO_EXTENSIONS):
            raise serializers.ValidationError(
                f"Service recordings must be a video file ({', '.join(self.VIDEO_EXTENSIONS)})."
            )
        if value.size > self.MAX_VIDEO_SIZE_BYTES:
            def human(num_bytes):
                mb = num_bytes / (1024 * 1024)
                return f"{mb / 1024:.2f}GB" if mb >= 1024 else f"{mb:.1f}MB"

            raise serializers.ValidationError(
                f"Recordings must be under {human(self.MAX_VIDEO_SIZE_BYTES)} "
                f"(this one is {human(value.size)})."
            )
        return value

    def validate_ticket(self, ticket):
        request = self.context.get("request")
        user = request.user if request else None
        if user is not None and not user.is_soori_admin and ticket.client_id != user.client_id:
            raise serializers.ValidationError("You do not have access to this ticket.")
        return ticket

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None
        if user is None:
            return attrs

        incoming = set(self.initial_data.keys())

        # Writing the customer-facing summary is a separate, more
        # senior act than writing the report itself -- it's the moment
        # something leaves the organisation.
        if incoming & {"customer_summary"}:
            if not user.has_staff_perm(StaffPermission.APPROVE_SERVICE_REPORT):
                raise serializers.ValidationError({
                    "customer_summary": "Only someone who can approve reports may write the customer summary."
                })

        # A recording with no title is unfindable in the training
        # library later -- camera filenames like "IMG_0042.mp4" tell an
        # intern nothing. So a title is required alongside a video.
        submitting_video = attrs.get("service_video") is not None
        has_title = bool((attrs.get("video_title") or getattr(self.instance, "video_title", "") or "").strip())
        if submitting_video and not has_title:
            raise serializers.ValidationError({
                "video_title": "Give the recording a title so it can be found in the Knowledge Base."
            })

        # The recording is required, not optional, and only on CREATION
        # -- a report is always first filed by the engineer who
        # attended (perform_create sets `engineer`), so this can never
        # incorrectly block the Service Department's later edit to
        # customer_summary, which doesn't touch the video at all.
        if self.instance is None and attrs.get("service_video") is None:
            raise serializers.ValidationError({
                "service_video": "A recording of the visit is required to file a report."
            })

        internal_fields = {"work_performed", "root_cause", "parts_used", "internal_notes", "service_video"}
        if incoming & internal_fields:
            if not (
                user.has_staff_perm(StaffPermission.WRITE_SERVICE_REPORT)
                or user.has_staff_perm(StaffPermission.APPROVE_SERVICE_REPORT)
            ):
                raise serializers.ValidationError(
                    "Your role doesn't have permission to write service reports."
                )

        return attrs

    def create(self, validated_data):
        video = validated_data.get("service_video")
        if video is not None:
            validated_data["service_video_filename"] = video.name
        # Always true on creation, regardless of what was sent -- the
        # engineer is never asked to decide this. Training material is
        # the company's whole reason for filming the visit at all, so
        # it isn't an opt-in choice at the point of filing. The service
        # layer can still switch a specific report off afterwards
        # (ServiceReportPanel's toggle, a plain update -- this only
        # governs the value at CREATE time).
        validated_data["include_in_knowledge_base"] = True
        return super().create(validated_data)

    def update(self, instance, validated_data):
        video = validated_data.get("service_video")
        if video is not None:
            validated_data["service_video_filename"] = video.name
        return super().update(instance, validated_data)
