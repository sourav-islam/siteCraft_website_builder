from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.common.models import TimeStampedModel
from apps.common.validators import validate_file_size, validate_html_file_extension
from apps.sites.models import Site


class Page(TimeStampedModel):
    """
    Represents a single page of a website.
    Example:
        Home
        About
        Contact
        Blog
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name="pages",
    )

    title = models.CharField(max_length=150)

    slug = models.SlugField(max_length=160)


    html_file = models.FileField(
        upload_to="pages/html/",
        blank=True,
        null=True,
        validators=[validate_file_size, validate_html_file_extension],
        help_text="Published HTML source file for this page.",
    )

    meta_description = models.TextField(
        blank=True,
        default="",
        help_text="SEO meta description for this page.",
    )

    page_type = models.CharField(
        max_length=50,
        default="standard",
        help_text="Type classification (e.g. standard, blog, landing).",
    )

    is_homepage = models.BooleanField(default=False)

    is_published = models.BooleanField(default=False)

    is_enabled = models.BooleanField(
        default=True,
        help_text="Only enabled pages are included in publish.",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )


    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pages_created",
        help_text="User who initially created the page.",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pages_updated",
        help_text="User who last modified the page.",
    )

    class Meta:
        ordering = ["created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["site", "slug"],
                name="unique_page_slug_per_site",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.site.name} - {self.title}"