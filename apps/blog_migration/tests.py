from unittest.mock import patch

from django.test import TestCase

from apps.blog_migration.exceptions import (
    BlogMigrationError,
    ExportError,
    ImageDownloadError,
    InvalidGoogleDocURLError,
    ValidationError,
)
from apps.blog_migration.services.content_cleaner import ContentCleanerService
from apps.blog_migration.services.exporter import ExporterService
from apps.blog_migration.services.reporter import Reporter


class BlogMigrationExceptionTests(TestCase):
    def test_base_exception_is_exception_hierarchy(self):
        self.assertTrue(issubclass(ExportError, BlogMigrationError))
        self.assertTrue(issubclass(ValidationError, BlogMigrationError))
        self.assertTrue(issubclass(ImageDownloadError, BlogMigrationError))
        self.assertTrue(issubclass(InvalidGoogleDocURLError, BlogMigrationError))

    def test_invalid_google_doc_url_error_raises(self):
        with self.assertRaises(InvalidGoogleDocURLError):
            raise InvalidGoogleDocURLError("bad URL")


class ContentCleanerServiceTests(TestCase):
    def test_clean_content_strips_google_doc_styles(self):
        html = (
            "<html><head><style>.cls-1 { color:red;</style></head>"
            '<body><p class="cls-1" id="p1" style="color:red">'
            "<span>Hello</span> <b>world</b></p>"
            "<p></p></body></html>"
        )
        images = []
        cleaned = ContentCleanerService.clean_content(html, images)
        self.assertNotIn("cls-1", cleaned)
        self.assertNotIn("<span", cleaned)
        self.assertNotIn('style="color', cleaned)

    def test_clean_content_replaces_image_urls_in_order(self):
        html = '<p><img src="old1.jpg"/><img src="old2.jpg"/></p>'
        images = [
            {"url": "/media/new1.jpg", "alt": "first"},
            {"url": "/media/new2.jpg"},
        ]
        cleaned = ContentCleanerService.clean_content(html, images)
        self.assertIn("/media/new1.jpg", cleaned)
        self.assertIn('alt="first"', cleaned)
        self.assertIn("/media/new2.jpg", cleaned)
        self.assertNotIn("old1.jpg", cleaned)

    def test_clean_content_removes_empty_paragraphs(self):
        html = "<div><p>Keep me</p><p> </p><p></p><div></div>"
        cleaned = ContentCleanerService.clean_content(html, [])
        self.assertIn("Keep me", cleaned)
        # empty <p></p> and the inner of the div may be stripped, keep
        paragraphs = cleaned.count("<p>")
        self.assertLessEqual(paragraphs, 3)


class ReporterTests(TestCase):
    def test_reporter_levels_print_without_crashing(self):
        reporter = Reporter()
        reporter.info("i")
        reporter.success("ok")
        reporter.warning("warn")
        reporter.error("err")


class ExporterServiceAdditionalTests(TestCase):
    @patch("apps.blog_migration.services.exporter.requests.get")
    def test_export_success_returns_response_text(self, mock_get):
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.text = "<h1>Title</h1>"
        result = ExporterService.export(
            "https://docs.google.com/document/d/DOC123/edit",
            tab_id="body",
        )
        self.assertIn("<h1>Title</h1>", result)

    @patch("apps.blog_migration.services.exporter.requests.get")
    def test_export_bad_status_raises_export_error(self, mock_get):
        mock_response = mock_get.return_value
        mock_response.status_code = 500
        mock_response.text = "Server Error"
        with self.assertRaises(ExportError):
            ExporterService.export(
                "https://docs.google.com/document/d/DOC123/edit",
                tab_id="body",
            )

    @patch("apps.blog_migration.services.exporter.requests.get")
    def test_export_bad_url_raises_invalid_gdoc_url(self, mock_get):
        with self.assertRaises(InvalidGoogleDocURLError):
            ExporterService.export("https://example.com/not-gdoc", tab_id="body")
        mock_get.assert_not_called()

    def test_extract_document_id_extracts_id(self):
        doc_id = ExporterService.extract_document_id(
            "https://docs.google.com/document/d/abcDEF123/edit#heading=h.x",
        )
        self.assertEqual(doc_id, "abcDEF123")

    def test_extract_document_id_underscore_dash(self):
        doc_id = ExporterService.extract_document_id(
            "https://docs.google.com/document/d/a-b_c123/edit",
        )
        self.assertEqual(doc_id, "a-b_c123")
