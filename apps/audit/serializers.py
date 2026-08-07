from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", default=None, read_only=True)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "actor",
            "actor_username",
            "action",
            "field_name",
            "old_value",
            "new_value",
            "metadata",
            "created_at",
        )
        read_only_fields = fields