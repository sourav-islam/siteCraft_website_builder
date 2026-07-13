from django.contrib import admin

from .models import Page


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "title",
        "site",
        "is_homepage",
        "is_published",
        "created_at",
    )

    list_filter = (
        "is_homepage",
        "is_published",
    )

    search_fields = (
        "title",
        "slug",
        "site__name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )