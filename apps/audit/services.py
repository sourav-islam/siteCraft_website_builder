import hashlib

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import File

from .models import AuditLog


def compute_hash(value):
    """
    Compute a SHA-256 hash for a value suitable for HTML/file change detection.

    - FileField/ImageField -> SHA-256 over file bytes.
    - None/empty -> consistent literal.
    - Strings -> SHA-256 over UTF-8 bytes.
    - Everything else -> SHA-256 over str(value).
    """
    if value is None or value == "":
        return "(empty)"

    if isinstance(value, File):
        hasher = hashlib.sha256()

        try:
            value.open("rb")
        except Exception:
            pass

        try:
            for chunk in value.chunks():
                hasher.update(chunk)
        except Exception:
            try:
                content = value.read()
                if isinstance(content, str):
                    content = content.encode("utf-8")
                hasher.update(content)
            except Exception:
                return "(unhashable)"
        finally:
            try:
                value.seek(0)
            except Exception:
                pass

        return hasher.hexdigest()

    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()

    if isinstance(value, str):
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def normalize_value(value):
    """
    Turn a model field value into a safe, comparable string for storage.

    - FileField/ImageField -> filename only, never bytes/content.
    - None / empty -> a consistent literal.
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

    Returns a dict keyed by field name:
    {"title": {"old": "aboutpage", "new": "a"}, ...}
    Safe to call before mutating `instance` — reads current values first.
    """
    changes = {}

    for field_name, new_raw in validated_data.items():
        old_raw = getattr(instance, field_name)

        if isinstance(old_raw, File) or isinstance(new_raw, File):
            old_value = compute_hash(old_raw)
            new_value = compute_hash(new_raw)
        else:
            old_value = normalize_value(old_raw)
            new_value = normalize_value(new_raw)

        if old_value != new_value:
            changes[field_name] = {
                "old": old_value,
                "new": new_value,
            }

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
    def _next_html_file_version(content_type, object_id):
        previous = (
            AuditLog.objects.filter(
                content_type=content_type,
                object_id=object_id,
                action=AuditLog.Action.UPDATED,
                metadata__has_key="html_file_version",
            )
            .order_by("-created_at")
            .first()
        )

        if not previous:
            return 1

        try:
            return int(previous.metadata.get("html_file_version", 0)) + 1
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def log_update(instance, actor, changes):
        """
        `changes` is the dict produced by diff_fields().
        Writes one row for the update action and stores all changed
        fields inside the JSON `changes` payload.
        No-ops (writes nothing) if `changes` is empty.
        """
        if not changes:
            return

        content_type = ContentType.objects.get_for_model(instance)

        metadata = {}
        if "html_file" in changes:
            html_hash = compute_hash(getattr(instance, "html_file", None))
            metadata = {
                "html_file_version": AuditService._next_html_file_version(
                    content_type, instance.pk
                ),
                "html_file_hash": html_hash,
            }

        AuditLog.objects.create(
            content_type=content_type,
            object_id=instance.pk,
            actor=actor,
            action=AuditLog.Action.UPDATED,
            changes=changes,
            metadata=metadata,
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