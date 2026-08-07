from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "client", "actor", "actor_username", "action", "target_type", "target_id", "metadata", "created_at"]
        read_only_fields = fields
