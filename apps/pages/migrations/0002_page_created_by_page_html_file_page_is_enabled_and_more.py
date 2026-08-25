"""
Marker migration to preserve migration history consistency.

The original operations in this migration (created_by, updated_by, html_file,
is_enabled, meta_description, page_type, status fields) were consolidated into
0001_initial after the fact. This file exists so that existing databases that
already applied the original 0002 do not end up with a "migration file missing"
state.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0001_initial"),
    ]

    operations = []
