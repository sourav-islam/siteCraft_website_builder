from django.contrib.contenttypes.models import ContentType
from django.core.files.base import File

from .models import AuditLog


def normalize_value(value):
    """
    Turn a model field value into a safe, comparable string for storage.

    - FileField/ImageField -> filename only, never bytes/content.
      Covers BOTH the already-saved FieldFile on the instance AND the
      incoming raw upload (ContentFile/UploadedFile) from validated_data
      — both are subclasses of django.core.files.base.File, but only
      FieldFile is caught by an isinstance(FieldFile) check, so we check
      the shared base class instead.
    - None / empty -> a consistent literal, so diffs against blank are
      visible instead of silently comparing "" to None.
    - Everything else -> str(value).
    """
    if isinstance(value, File):
        return value.name if value.name else "(empty)"

    if value is None or value == "":
        return "(empty)"

    return str(value)


def diff_fields(instance, validated_data):
    """
    Compare an instance's current field values against incoming
    validated_data and return only the fields that actually changed.

    Returns a list of dicts: [{"field_name", "old_value", "new_value"}, ...]
    Safe to call before mutating `instance` — reads current values first.
    """
    changes = []

    for field_name, new_raw in validated_data.items():
        old_raw = getattr(instance, field_name)

        old_value = normalize_value(old_raw)
        new_value = normalize_value(new_raw)

        if old_value != new_value:
            changes.append(
                {
                    "field_name": field_name,
                    "old_value": old_value,
                    "new_value": new_value,
                }
            )

    return changes


class AuditService:
    """
    Single write surface for AuditLog. Nothing else should call
    AuditLog.objects.create()/bulk_create() directly.
    """

    @staticmethod
    def log_create(instance, actor):
        content_type = ContentType.objects.get_for_model(instance)
        AuditLog.objects.create(
            content_type=content_type,
            object_id=instance.pk,
            actor=actor,
            action=AuditLog.Action.CREATED,
        )

    @staticmethod
    def log_update(instance, actor, changes):
        """
        `changes` is the list of dicts produced by diff_fields().
        Writes one row per changed field in a single query.
        No-ops (writes nothing) if `changes` is empty.
        """
        if not changes:
            return

        content_type = ContentType.objects.get_for_model(instance)

        AuditLog.objects.bulk_create(
            [
                AuditLog(
                    content_type=content_type,
                    object_id=instance.pk,
                    actor=actor,
                    action=AuditLog.Action.UPDATED,
                    field_name=change["field_name"],
                    old_value=change["old_value"],
                    new_value=change["new_value"],
                )
                for change in changes
            ]
        )

    @staticmethod
    def log_delete(instance, actor, metadata=None):
        """
        Must be called BEFORE the instance is actually deleted, since
        object_id needs a real, still-valid PK to point at.
        """
        content_type = ContentType.objects.get_for_model(instance)
        AuditLog.objects.create(
            content_type=content_type,
            object_id=instance.pk,
            actor=actor,
            action=AuditLog.Action.DELETED,
            metadata=metadata or {},
        )

    @staticmethod
    def log_action(instance, actor, action, metadata=None):
        """
        Generic catch-all for action types that aren't create/update/delete
        (e.g. "published", "locked", "unlocked").
        """
        content_type = ContentType.objects.get_for_model(instance)
        AuditLog.objects.create(
            content_type=content_type,
            object_id=instance.pk,
            actor=actor,
            action=action,
            metadata=metadata or {},
        )