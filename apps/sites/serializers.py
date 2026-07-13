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
        )

        fields = "__all__"