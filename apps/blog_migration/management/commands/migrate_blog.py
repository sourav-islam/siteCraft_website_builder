from django.core.management.base import BaseCommand

from apps.blog_migration.services.exporter import ExporterService
from apps.blog_migration.services.parser import ParserService
from apps.blog_migration.services.image_downloader import ImageDownloaderService
from apps.blog_migration.services.content_cleaner import ContentCleanerService
from apps.blog_migration.models import BlogPost
from apps.blog_migration.services.reporter import Reporter


class Command(BaseCommand):
    help = "Migrate a blog from Google Docs."

    def add_arguments(self, parser):
        parser.add_argument(
            "url",
            type=str,
            help="Google Docs URL",
        )
        parser.add_argument(
            "--site-id",
            type=int,
            help="Optional Site ID to associate with the blog post",
            default=None,
        )

    def handle(self, *args, **options):
        url = options["url"]
        site_id = options["site_id"]

        Reporter.info("Starting export...")
        html = ExporterService.export(url)
        Reporter.success("HTML exported successfully.")

        Reporter.info("Parsing HTML...")
        parsed_data = ParserService.parse_google_doc_html(html)
        Reporter.success(f"Parsed: Title - '{parsed_data['title']}', {len(parsed_data['images'])} images")

        Reporter.info("Creating blog post...")
        blog_post = BlogPost.objects.create(
            title=parsed_data["title"],
            html_content=parsed_data["content"],
            site_id=site_id
        )
        Reporter.success(f"Blog post created with ID: {blog_post.id}")

        Reporter.info("Downloading images...")
        blog_images = ImageDownloaderService.download_images(blog_post, parsed_data["images"])
        Reporter.success(f"Downloaded {len(blog_images)} images")

        Reporter.info("Cleaning content...")
        cleaned_content = ContentCleanerService.clean_content(
            parsed_data["content"],
            blog_images
        )
        blog_post.html_content = cleaned_content
        blog_post.save()
        Reporter.success("Content cleaned and saved")

        Reporter.success("Blog migration completed!")
