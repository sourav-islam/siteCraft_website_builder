from django.contrib import admin
from apps.blog_migration.models import BlogPost, BlogImage


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "is_published", "created_at"]
    list_filter = ["is_published", "created_at"]
    search_fields = ["title", "content"]
    prepopulated_fields = {"slug": ("title",)}


@admin.register(BlogImage)
class BlogImageAdmin(admin.ModelAdmin):
    list_display = ["blog_post", "created_at"]
    list_filter = ["created_at"]

