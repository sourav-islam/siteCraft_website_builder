from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.common.upload_paths import environment_upload_path
from apps.common.validators import (
    validate_css_file_extension,
    validate_file_size,
    validate_html_file_extension,
)


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
        upload_to=environment_upload_path,
        blank=True,
        null=True,
    )

    favicon = models.ImageField(
        upload_to=environment_upload_path,
        blank=True,
        null=True,
    )

    header = models.FileField(
        upload_to=environment_upload_path,
        blank=True,
        null=True,
        validators=[validate_file_size, validate_html_file_extension],
        help_text="Header HTML file for the published site.",
    )

    footer = models.FileField(
        upload_to=environment_upload_path,
        blank=True,
        null=True,
        validators=[validate_file_size, validate_html_file_extension],
        help_text="Footer HTML file for the published site.",
    )

    global_css = models.FileField(
        upload_to=environment_upload_path,
        blank=True,
        null=True,
        validators=[validate_file_size, validate_css_file_extension],
        help_text="Global CSS file for the published site.",
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


class SiteVersion(models.Model):
    class Status(models.TextChoices):
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name="versions",
    )

    version_number = models.PositiveIntegerField()

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_versions_created",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.FAILED,
    )

    class Meta:
        ordering = ["version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["site", "version_number"],
                name="unique_site_version_number",
            ),
        ]

    def __str__(self):
        return f"{self.site.name} - Version {self.version_number}"
