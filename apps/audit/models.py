from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.common.models import TimeStampedModel


class AuditLog(TimeStampedModel):
    """
    Generic, append-only record of who did what to which object and when.

    One row per action for updated/created/deleted/published events.
    Never mutated after creation.
    """

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        DELETED = "deleted", "Deleted"
        PUBLISHED = "published", "Published"
        ROLLED_BACK = "rolled_back", "Rolled back"
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

    changes = models.JSONField(
        blank=True,
        default=dict,
        help_text=(
            "Field-level diff payload for update actions, keyed by field name. "
            "Example: {'title': {'old': 'aboutpage', 'new': 'a'}}"
        ),
    )

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
        return f"{self.action} on {self.content_type}#{self.object_id}"