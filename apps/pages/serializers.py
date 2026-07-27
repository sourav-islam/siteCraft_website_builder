from rest_framework import serializers
import os

from apps.sites.models import Site
from apps.sites.serializers import _abs_url

from .models import Page


class PageSerializer(serializers.ModelSerializer):
    """
    Learning-mode Page serializer (medium payload):
      - page info
      - nested site: {id, name, detail_url, header_url, footer_url}
      - created_by / updated_by: username string + id
      - html_file_url, detail_url
    """

    # --- Relations ---
    # Read: medium nested site dict (name + urls, id)
    site = serializers.SerializerMethodField()
    # Write: integer pk
    site_id = serializers.PrimaryKeyRelatedField(
        queryset=Site.objects.all(), source="site", write_only=True, required=True,
    )

    # --- Audit (simple scalar fields, no MiniUser class) ---
    created_by_id = serializers.SerializerMethodField()
    created_by_username = serializers.SerializerMethodField()
    updated_by_id = serializers.SerializerMethodField()
    updated_by_username = serializers.SerializerMethodField()

    # --- URLs ---
    html_file_url = serializers.SerializerMethodField()
    detail_url = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = (
            # Identity + relation
            "id", "site", "site_id", "detail_url",
            # Data
            "title", "slug", "content",
            "html_file", "html_file_url",
            "meta_description", "page_type",
            # Flags + status
            "is_homepage", "is_enabled", "is_published", "status",
            # Audit
            "created_by_id", "created_by_username",
            "updated_by_id", "updated_by_username",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "created_at", "updated_at",
            "created_by_id", "created_by_username",
            "updated_by_id", "updated_by_username",
            "is_published", "status",
        )

    # ---------- nested site (name + urls + id) ----------------------
    def get_site(self, obj):
        req = self.context.get("request")
        if not obj.site:
            return None
        from django.urls import reverse
        return {
            "id": obj.site.id,
            "name": obj.site.name,
            "detail_url": req.build_absolute_uri(reverse("site-detail", args=[obj.site.id])) if req else None,
            "header_url": _abs_url(req, obj.site.header),
            "footer_url": _abs_url(req, obj.site.footer),
        }

    # ---------- audit scalars ----------------------------------------
    def get_created_by_id(self, o):       return o.created_by_id
    def get_created_by_username(self, o): return o.created_by.username if o.created_by else None
    def get_updated_by_id(self, o):       return o.updated_by_id
    def get_updated_by_username(self, o): return o.updated_by.username if o.updated_by else None

    # ---------- urls -------------------------------------------------
    def get_html_file_url(self, o):
        return _abs_url(self.context.get("request"), o.html_file)

    def get_detail_url(self, o):
        req = self.context.get("request")
        if not req: return None
        from django.urls import reverse
        return req.build_absolute_uri(reverse("page-detail", args=[o.id]))

    # ---------- validators -------------------------------------------
    def validate_html_file(self, v):
        if v and not v.name.lower().endswith((".html", ".htm")):
            raise serializers.ValidationError("Only .html / .htm files allowed.")
        return v

    def validate_site_id(self, value):
        """Pages only in sites you own."""
        req = self.context.get("request")
        if req and value.owner != req.user:
            raise serializers.ValidationError("You do not own this site.")
        return value

    def validate(self, attrs):
        """Max 1 homepage per site."""
        site = attrs.get("site", getattr(self.instance, "site", None))
        hp = attrs.get("is_homepage", getattr(self.instance, "is_homepage", False))
        if site and hp:
            qs = Page.objects.filter(site=site, is_homepage=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "is_homepage": "This site already has a homepage."
                })
        return attrs