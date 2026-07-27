from django.core.exceptions import ValidationError
import os

def validate_file_size(file, max_size_mb=5):
    """
    Validate uploaded file size.
    """

    if file.size > max_size_mb * 1024 * 1024:
        raise ValidationError(
            f"File size cannot exceed {max_size_mb} MB."
        )


def validate_html_file_extension(file):
    """
    Validate that an uploaded file has a .html extension.
    """

    allowed_extensions = (".html", ".htm")
    filename = getattr(file, "name", "")
    ext = os.path.splitext(filename)[1].lower()

    if ext not in allowed_extensions:
        raise ValidationError(
            "Only .html and .htm files are allowed."
        )