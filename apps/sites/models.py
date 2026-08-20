from django.conf import settings
from django.db import models

from apps.common.validators import validate_file_size, validate_html_file_extension

from apps.common.models import TimeStampedModel


class Site(TimeStampedModel):
    """
    Represents a single website.
    Example:
        siteCraft
        MyBlog
        MyPortfolio
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sites",
    )

    name = models.CharField(max_length=150)

    description = models.TextField(blank=True)

    logo = models.ImageField(
        upload_to="sites/logos/",
        blank=True,
        null=True,
    )

    favicon = models.ImageField(
        upload_to="sites/favicons/",
        blank=True,
        null=True,
    )

    header = models.FileField(
        upload_to="sites/header/",
        blank=True,
        null=True,
        validators=[validate_file_size, validate_html_file_extension],
        help_text="Header HTML file for the published site.",
    )

    footer = models.FileField(
        upload_to="sites/footer/",
        blank=True,
        null=True,
        validators=[validate_file_size, validate_html_file_extension],
        help_text="Footer HTML file for the published site.",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    is_public = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sites_created",
        help_text="User who initially created the site.",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sites_updated",
        help_text="User who last modified the site.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name