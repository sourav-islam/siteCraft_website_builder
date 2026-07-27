from rest_framework import serializers
import os

from .models import Site


def _abs_url(request, file_field):
    if not request or not file_field:
        return None
    return request.build_absolute_uri(file_field.url)


class SiteSerializer(serializers.ModelSerializer):

    # URLs (read-only)
    logo_url = serializers.SerializerMethodField()
    favicon_url = serializers.SerializerMethodField()
    header_url = serializers.SerializerMethodField()
    footer_url = serializers.SerializerMethodField()
    detail_url = serializers.SerializerMethodField()
    page_count = serializers.SerializerMethodField()

    # Owner/audit — simple {id, username} dict via SerializerMethodField (no mini classes)
    owner_id = serializers.SerializerMethodField()
    owner_username = serializers.SerializerMethodField()
    created_by_username = serializers.SerializerMethodField()
    updated_by_username = serializers.SerializerMethodField()

    class Meta:
        model = Site
        fields = (
            "id",
            "name",
            "description",
            "status",
            "is_public",
            "logo",       "logo_url",
            "favicon",    "favicon_url",
            "header",     "header_url",
            "footer",     "footer_url",
            "owner_id", "owner_username",
            "created_by_username",
            "updated_by_username",
            "created_at",
            "updated_at",
            "page_count",
            "detail_url",
        )
        read_only_fields = ("id", "created_at", "updated_at", "page_count")

    # --- URL helpers ---
    def get_logo_url(self, o):    return _abs_url(self.context.get("request"), o.logo)
    def get_favicon_url(self, o): return _abs_url(self.context.get("request"), o.favicon)
    def get_header_url(self, o):  return _abs_url(self.context.get("request"), o.header)
    def get_footer_url(self, o):  return _abs_url(self.context.get("request"), o.footer)

    def get_detail_url(self, o):
        req = self.context.get("request")
        if not req: return None
        from django.urls import reverse
        return req.build_absolute_uri(reverse("site-detail", args=[o.id]))

    def get_page_count(self, o):  return o.pages.count()

    # --- Audit helpers (no nested serializer classes) ---
    def get_owner_id(self, o):            return o.owner_id
    def get_owner_username(self, o):      return o.owner.username if o.owner else None
    def get_created_by_username(self, o): return o.created_by.username if o.created_by else None
    def get_updated_by_username(self, o): return o.updated_by.username if o.updated_by else None

    # --- .html extension validation (Q2 choice) at serializer level ---
    @staticmethod
    def _check_html(value, fname):
        if not value: return
        if not value.name.lower().endswith((".html", ".htm")):
            raise serializers.ValidationError({fname: "Only .html / .htm files allowed."})

    def validate_header(self, v):  self._check_html(v, "header"); return v
    def validate_footer(self, v):  self._check_html(v, "footer"); return v