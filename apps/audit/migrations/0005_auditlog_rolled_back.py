from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0004_remove_auditlog_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("created", "Created"),
                    ("updated", "Updated"),
                    ("deleted", "Deleted"),
                    ("published", "Published"),
                    ("rolled_back", "Rolled back"),
                    ("locked", "Locked"),
                    ("unlocked", "Unlocked"),
                ],
                max_length=20,
            ),
        ),
    ]
