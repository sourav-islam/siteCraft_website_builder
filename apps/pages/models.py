from django.db import models
from django.utils.text import slugify

from apps.sites.models import Site


class Page(models.Model):
    """
    Represents a single page of a website.
    Example:
        Home
        About
        Contact
        Blog
    """

    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name="pages",
    )

    title = models.CharField(max_length=150)

    slug = models.SlugField(max_length=160)

    content = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores builder sections/components as JSON.",
    )

    is_homepage = models.BooleanField(default=False)

    is_published = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

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