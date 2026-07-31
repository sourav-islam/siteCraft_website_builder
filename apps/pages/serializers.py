from rest_framework import serializers

from apps.sites.models import Site

from .models import Page


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page

        fields = (
            "id",
            "site",
            "title",
            "slug",
            "html_file",
            "is_homepage",
            "is_published",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )

 
    def validate(self, attrs):
        """
        Only one homepage is allowed per site.
        Site now comes from the URL (via context), not the request body.
        """

        site = self.context.get("site") or getattr(self.instance, "site", None)

        is_homepage = attrs.get(
            "is_homepage",
            getattr(self.instance, "is_homepage", False),
        )

        if site and is_homepage:

            queryset = Page.objects.filter(
                site=site,
                is_homepage=True,
            )

            if self.instance:
                queryset = queryset.exclude(
                    pk=self.instance.pk
                )

            if queryset.exists():
                raise serializers.ValidationError(
                    {
                        "is_homepage":
                        "This site already has a homepage."
                    }
                )

        return attrs