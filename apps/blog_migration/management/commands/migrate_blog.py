from django.core.management.base import BaseCommand

from apps.blog_migration.services.exporter import ExporterService
from apps.blog_migration.services.reporter import Reporter


class Command(BaseCommand):
    help = "Migrate a blog."

    def add_arguments(self, parser):
        parser.add_argument(
            "url",
            type=str,
            help="Google Docs URL",
        )

    def handle(self, *args, **options):
        url = options["url"]

        Reporter.info("Starting export...")

        html = ExporterService.export(url)

        Reporter.success("HTML exported successfully.")

        Reporter.info(f"Downloaded {len(html)} characters.")