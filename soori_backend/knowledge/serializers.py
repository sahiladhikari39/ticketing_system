from django.utils import timezone
from rest_framework import serializers

from tickets.models import ServiceReport

from .models import AccessCode, AccessCodeScope


class AccessCodeSerializer(serializers.ModelSerializer):
    """Listing/managing codes, for the staff who issue them."""

    status = serializers.CharField(read_only=True)
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    customer_username = serializers.CharField(source="customer.username", read_only=True, default=None)
    issued_by_username = serializers.CharField(source="issued_by.username", read_only=True, default=None)

    class Meta:
        model = AccessCode
        fields = [
            "id", "scope", "scope_display", "label", "username",
            "customer", "customer_username", "issued_by", "issued_by_username",
            "recipient_email",
            "created_at", "expires_at", "revoked_at",
            "max_uses", "use_count", "last_used_at", "status",
        ]
        # `username` is generated, never chosen. The secret half is
        # absent from this list entirely -- it exists only in the
        # one-time creation response, and is not recoverable after.
        read_only_fields = [
            "id", "username", "issued_by", "created_at", "revoked_at",
            "use_count", "last_used_at", "status",
        ]

    def validate_expires_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("The expiry date has to be in the future.")
        return value

    def validate(self, attrs):
        scope = attrs.get("scope")
        customer = attrs.get("customer")

        if scope in (AccessCodeScope.CUSTOMER_HISTORY, AccessCodeScope.ENGINEER_HISTORY) and customer is None:
            raise serializers.ValidationError({
                "customer": "Pick which customer's history this code should unlock."
            })
        if scope == AccessCodeScope.KNOWLEDGE_BASE and customer is not None:
            raise serializers.ValidationError({
                "customer": "Knowledge Base codes aren't tied to a customer -- leave this blank."
            })

        # Never let a code be issued against a customer at a different
        # company than the person issuing it.
        request = self.context.get("request")
        if customer is not None and request is not None:
            if customer.client_id != request.user.client_id:
                raise serializers.ValidationError({"customer": "That customer isn't in your organisation."})

        return attrs


class KnowledgeBaseEntrySerializer(serializers.ModelSerializer):
    """
    A service report as TRAINING material.

    Strips everything that identifies the customer -- an intern
    learning how a fuser unit is replaced has no need to know whose
    printer it was, and spreading customer identities across every
    trainee is exactly the kind of quiet privacy problem nobody
    notices until it matters. What's left is the technical content,
    which is the whole point.
    """

    service_video_url = serializers.SerializerMethodField()
    equipment = serializers.CharField(source="ticket.product_or_service", read_only=True)
    problem = serializers.CharField(source="ticket.title", read_only=True)

    class Meta:
        model = ServiceReport
        fields = [
            "id", "video_title", "equipment", "problem",
            "work_performed", "root_cause", "parts_used",
            "service_video_url", "created_at",
        ]
        read_only_fields = fields
        # Deliberately absent: ticket id, customer, engineer name,
        # internal_notes, customer_summary. internal_notes especially --
        # it's where staff write blunt commentary about the customer.

    def get_service_video_url(self, obj):
        request = self.context.get("request")
        if not obj.service_video:
            return None
        return request.build_absolute_uri(obj.service_video.url) if request else obj.service_video.url


class CustomerHistoryEntrySerializer(serializers.ModelSerializer):
    """
    A customer's own service history. Only ever the released summary --
    identical restriction to what a logged-in customer sees, so a code
    can't be used as a way around it.
    """

    equipment = serializers.CharField(source="ticket.product_or_service", read_only=True)
    problem = serializers.CharField(source="ticket.title", read_only=True)
    ticket_status = serializers.CharField(source="ticket.status", read_only=True)

    class Meta:
        model = ServiceReport
        fields = [
            "id", "equipment", "problem", "ticket_status",
            "customer_summary", "shared_with_customer_at",
        ]
        read_only_fields = fields


class EngineerHistoryEntrySerializer(serializers.ModelSerializer):
    """
    Full technical detail from a customer's past visits -- for an
    engineer preparing for a new one, via an APPROVED
    HistoryAccessRequest. Deliberately more detailed than
    CustomerHistoryEntrySerializer (the customer's own view): a repeat
    fault is useless to diagnose from a one-line summary.

    Still excludes internal_notes on purpose. That field holds staff
    commentary -- sometimes about things unrelated to the technical
    fault -- and opening it to a DIFFERENT engineer than the one who
    wrote it wasn't part of what this feature was asked to do. Also
    excludes the video: watching another engineer's on-site recording
    is a Knowledge Base concern (a different scope, a different
    purpose -- training, not job prep), not this one.
    """

    equipment = serializers.CharField(source="ticket.product_or_service", read_only=True)
    problem = serializers.CharField(source="ticket.title", read_only=True)
    engineer_username = serializers.CharField(source="engineer.username", read_only=True, default=None)

    class Meta:
        model = ServiceReport
        fields = [
            "id", "equipment", "problem", "engineer_username",
            "work_performed", "root_cause", "parts_used", "created_at",
        ]
        read_only_fields = fields
