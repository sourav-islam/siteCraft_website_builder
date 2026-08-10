"""
Drop the legacy 'content' (jsonb) column from pages_page.

This column is no longer represented on the Page model (page content lives in
the uploaded html_file now) and was left behind after an in-place rewrite of
0001_initial. Uses raw SQL because the field no longer exists on the model so
RemoveField cannot auto-generate.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0002_page_created_by_page_html_file_page_is_enabled_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE pages_page DROP COLUMN IF EXISTS content;",
            reverse_sql=(
                "ALTER TABLE pages_page ADD COLUMN content jsonb "
                "DEFAULT '{}'::jsonb NOT NULL;"
            ),
        ),
    ]
