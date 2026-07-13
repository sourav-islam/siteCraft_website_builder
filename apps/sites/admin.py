from django.contrib import admin

from .models import Site


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "owner",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "is_public",
    )

    search_fields = (
        "name",
        "description",

    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )