from .html_minifier import HTMLMinifier
from .html_to_json import HTMLToJSONConverter
from .publish_service import PublishService


# ---------- simple audit-aware create/update (learning version) ----------
# Replaces the old flat apps/sites/services.py and apps/pages/services.py
from apps.sites.models import Site
from django.utils.text import slugify


class SiteService:
    @staticmethod
    def create_site(owner, **vd):
        return Site.objects.create(
            owner=owner,
            created_by=vd.pop("created_by", owner),
            updated_by=vd.pop("updated_by", owner),
            **vd,
        )

    @staticmethod
    def update_site(instance, **vd):
        for f, v in vd.items():
            setattr(instance, f, v)
        instance.save()
        return instance


class PageService:
    @staticmethod
    def create_page(**vd):
        from apps.pages.models import Page

        site = vd.get("site")
        title = vd.get("title") or ""
        base_slug = vd.get("slug") or slugify(title)
        slug = base_slug
        i = 1
        if site:
            while Page.objects.filter(site=site, slug=slug).exists():
                slug = f"{base_slug}-{i}"
                i += 1
        vd["slug"] = slug
        if vd.get("created_by") is None and site:
            vd["created_by"] = site.owner
        if vd.get("updated_by") is None:
            vd["updated_by"] = vd.get("created_by")
        return Page.objects.create(**vd)

    @staticmethod
    def update_page(instance, **vd):
        for f, v in vd.items():
            setattr(instance, f, v)
        instance.save()
        return instance