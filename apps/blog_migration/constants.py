# from pathlib import Path

# OUTPUT_DIR = Path("media/migration")

# RAW_HTML_FILE = OUTPUT_DIR / "raw.html"
# CLEAN_HTML_FILE = OUTPUT_DIR / "clean.html"

# IMAGES_DIR = OUTPUT_DIR / "images"

from pathlib import Path

MEDIA_ROOT = Path("media")

MIGRATION_DIR = MEDIA_ROOT / "migration"

RAW_HTML_FILE = MIGRATION_DIR / "raw.html"

GOOGLE_DOC_EXPORT_URL = (
    "https://docs.google.com/document/d/{doc_id}/export?format=html"
)