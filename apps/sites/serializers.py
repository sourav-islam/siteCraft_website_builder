from rest_framework import serializers

from .models import Site


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