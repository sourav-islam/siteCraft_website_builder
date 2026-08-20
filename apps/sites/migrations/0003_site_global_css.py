import apps.common.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sites", "0002_site_created_by_site_footer_site_header_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="site",
            name="global_css",
            field=models.FileField(
                blank=True,
                help_text="Global CSS file for the published site.",
                null=True,
                upload_to="sites/global_css/",
                validators=[
                    apps.common.validators.validate_file_size,
                    apps.common.validators.validate_css_file_extension,
                ],
            ),
        ),
    ]