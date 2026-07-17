from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.blog_migration.services.exporter import ExporterService
from apps.blog_migration.services.parser import ParserService
from apps.blog_migration.services.image_downloader import ImageDownloaderService
from apps.blog_migration.services.content_cleaner import ContentCleanerService
from apps.blog_migration.services.reporter import Reporter
from apps.pages.services import PageService


class Command(BaseCommand):
    help = "Migrate blog tabs from a public Google Docs URL into Page rows."

    def add_arguments(self, parser):
        parser.add_argument("url", type=str, help="Google Docs URL")
        parser.add_argument("--site-id", type=int, required=True,
                             help="Site ID to associate with the migrated pages")
        parser.add_argument("--tabs", type=str, required=True,
                             help="Comma-separated Google Docs tab IDs, e.g. t.0,t.1,t.2")

    def handle(self, *args, **options):
        url = options["url"]
        site_id = options["site_id"]
        tab_ids = [t.strip() for t in options["tabs"].split(",") if t.strip()]

        if not tab_ids:
            raise CommandError("No tab IDs provided.")

        created, failed = 0, 0
        for tab_id in tab_ids:
            try:
                self._migrate_tab(url, tab_id, site_id)
                created += 1
            except Exception as e:
                Reporter.error(f"Tab {tab_id} failed: {e}")
                failed += 1

        Reporter.success(f"Migration finished. {created} page(s) created, {failed} failed.")

    def _migrate_tab(self, url: str, tab_id: str, site_id: int):
        Reporter.info(f"[{tab_id}] Exporting...")
        html = ExporterService.export(url, tab_id)

        Reporter.info(f"[{tab_id}] Parsing...")
        parsed = ParserService.parse_google_doc_html(html)
        Reporter.success(f"[{tab_id}] '{parsed['title']}', {len(parsed['images'])} image(s)")

        Reporter.info(f"[{tab_id}] Downloading images...")
        images = ImageDownloaderService.download_images(
            parsed["images"], folder=slugify(parsed["title"]) or tab_id
        )

        Reporter.info(f"[{tab_id}] Cleaning content...")
        cleaned_html = ContentCleanerService.clean_content(parsed["content"], images)

        Reporter.info(f"[{tab_id}] Creating page...")
        page = PageService.create_page(
            site_id=site_id,
            title=parsed["title"],
            slug=slugify(parsed["title"]),
            content={"html": cleaned_html},
            is_published=False,
            is_homepage=False,
        )
        Reporter.success(f"[{tab_id}] Page created with ID: {page.id}")
