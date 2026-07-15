class BlogMigrationError(Exception):
    """Base exception for blog migration."""


class ExportError(BlogMigrationError):
    """Raised when exporting/fetching HTML fails."""


class ValidationError(BlogMigrationError):
    """Raised when parsed content is invalid."""


class ImageDownloadError(BlogMigrationError):
    """Raised when an image cannot be downloaded."""

class InvalidGoogleDocURLError(BlogMigrationError):
    """Invalid Google Docs URL."""    