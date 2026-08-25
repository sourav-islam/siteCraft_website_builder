from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def environment_upload_path(instance, filename):
    """Return a model-relative path under the active environment media root."""

    app_env = getattr(settings, "APP_ENV", "")
    allowed_environments = getattr(
        settings,
        "ALLOWED_APP_ENVIRONMENTS",
        ("canary", "beta", "production"),
    )
    if app_env not in allowed_environments:
        allowed = ", ".join(allowed_environments)
        raise ImproperlyConfigured(f"APP_ENV must be one of: {allowed}.")

    return f"{instance._meta.model_name}/{filename}"
