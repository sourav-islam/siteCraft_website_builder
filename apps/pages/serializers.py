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
            "content",
            "is_homepage",
            "is_published",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
        )

    def validate_site(self, value):
        """
        A user can only create pages
        inside their own sites.
        """

        request = self.context["request"]

        if value.owner != request.user:
            raise serializers.ValidationError(
                "You do not own this site."
            )

        return value

    def validate(self, attrs):
        """
        Only one homepage is allowed per site.
        """

        site = attrs.get(
            "site",
            getattr(self.instance, "site", None),
        )

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