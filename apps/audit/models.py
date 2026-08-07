from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.common.models import TimeStampedModel


class AuditLog(TimeStampedModel):
    """
    Generic, append-only record of who did what to which object and when.

    One row per changed field on an "updated" action, one row per
    action for everything else (created / deleted / published / ...).
    Never mutated after creation.
    """

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        DELETED = "deleted", "Deleted"
        PUBLISHED = "published", "Published"
        LOCKED = "locked", "Locked"
        UNLOCKED = "unlocked", "Unlocked"

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text="User who performed the action. Null if the system performed it.",
    )

    action = models.CharField(
        max_length=20,
        choices=Action.choices,
    )

    field_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Populated only for 'updated' rows — the field that changed.",
    )

    old_value = models.TextField(blank=True, default="")
    new_value = models.TextField(blank=True, default="")

    metadata = models.JSONField(
        blank=True,
        default=dict,
        help_text="Free-form context for action types that aren't a simple field diff.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id", "-created_at"]),
        ]

    def __str__(self):
        if self.field_name:
            return f"{self.action}:{self.field_name} on {self.content_type}#{self.object_id}"
        return f"{self.action} on {self.content_type}#{self.object_id}"