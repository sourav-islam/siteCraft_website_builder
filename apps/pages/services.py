from django.utils.text import slugify
from apps.audit.services import AuditService, diff_fields
from .models import Page


class PageService:
    """
    Business logic for Page operations.
    """

    @staticmethod
    def create_page(**validated_data):
        # Get site from either site or site_id
        site = validated_data.get("site")
        site_id = validated_data.get("site_id")

        title = validated_data.get("title")
        base_slug = validated_data.get("slug") or slugify(title)
        slug = base_slug
        counter = 1

        # Check if slug already exists for this site
        if site:
            filter_kwargs = {"site": site}
        elif site_id:
            filter_kwargs = {"site_id": site_id}
        else:
            # No site provided, just use the slug as is
            pass

        if filter_kwargs:
            while Page.objects.filter(**filter_kwargs, slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

        validated_data["slug"] = slug
        page = Page.objects.create(**validated_data)

        actor = validated_data.get("created_by")
        AuditService.log_create(page, actor)

        return page

    @staticmethod
    def update_page(instance, **validated_data):
        changes = diff_fields(instance, validated_data)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()

        actor = validated_data.get("updated_by")
        AuditService.log_update(instance, actor, changes)

        return instance