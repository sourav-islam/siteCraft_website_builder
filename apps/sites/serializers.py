from rest_framework import serializers

from .models import Site, SiteVersion


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site

        read_only_fields = (
            "id",
            "owner",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )

        fields = "__all__"


class SiteRollbackSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class SiteVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteVersion
        fields = (
            "id",
            "site",
            "version_number",
            "created_by",
            "created_at",
            "status",
        )
        read_only_fields = fields
