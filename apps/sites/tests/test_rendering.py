import json
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase, override_settings
from django.test.client import RequestFactory

from apps.sites.models import Site
from apps.sites.services.render_service import PublishedSiteRenderService


class PublishedSiteRenderingTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override_media = override_settings(MEDIA_ROOT=self.media_root)
        self.override_media.enable()
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="render-owner",
            email="render-owner@example.com",
            password="password",
        )
        self.site = Site.objects.create(owner=self.owner, name="Sonder")
        self.service = PublishedSiteRenderService()
        self.request = RequestFactory().get("/sites/1/published/")

    def tearDown(self):
        self.override_media.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _write(self, relative_path, content):
        path = Path(self.media_root) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _write_json(self, relative_path, data):
        self._write(relative_path, json.dumps(data))

    def _create_version(self, version, label):
        root = f"published/sonder-{self.site.id}/versions/{version}"
        self._write_json(
            f"{root}/manifest.json",
            {
                "version": version,
                "files": {
                    "header": "header.json",
                    "footer": "footer.json",
                    "global_css": "global.css",
                    "pages": {"home": "pages/home.json"},
                },
            },
        )
        self._write_json(
            f"{root}/header.json",
            {"html": f"<header>{label} header</header>"},
        )
        self._write_json(
            f"{root}/pages/home.json",
            {
                "title": f"{label} home",
                "meta_description": f"{label} description",
                "html": f"<main>{label} homepage</main>",
            },
        )
        self._write_json(
            f"{root}/footer.json",
            {"html": f"<footer>{label} footer</footer>"},
        )
        self._write(f"{root}/global.css", f"body {{ color: {label}; }}")

    def _set_current(self, version):
        self._write_json(
            f"published/sonder-{self.site.id}/current.json",
            {"version": version},
        )

    def test_rendered_site_uses_current_version_for_all_content(self):
        self._create_version(1, "version-one")
        self._create_version(2, "version-two")
        self._set_current(2)

        response = self.service.render_homepage(self.request, self.site)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("version-two header", content)
        self.assertIn("version-two homepage", content)
        self.assertIn("version-two footer", content)
        self.assertIn("body { color: version-two; }", content)
        self.assertNotIn("version-one", content)

    def test_published_site_url_returns_rendered_html(self):
        self._create_version(1, "version-one")
        self._set_current(1)
        response = self.client.get(f"/sites/{self.site.id}/published/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "version-one homepage")

    def test_published_page_slug_url_renders_manifest_page(self):
        self._create_version(1, "version-one")
        version_root = f"published/sonder-{self.site.id}/versions/1"
        manifest_path = Path(self.media_root) / f"{version_root}/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["pages"]["about"] = "pages/about.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self._write_json(
            f"{version_root}/pages/about.json",
            {
                "title": "About",
                "meta_description": "About page",
                "html": "<main>About page content</main>",
            },
        )
        self._set_current(1)
        response = self.client.get(f"/sites/{self.site.id}/published/about")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "About page content")
        self.assertNotContains(response, "version-one homepage")

    def test_unknown_published_page_slug_returns_404(self):
        self._create_version(1, "version-one")
        self._set_current(1)
        response = self.client.get(f"/sites/{self.site.id}/published/missing")

        self.assertEqual(response.status_code, 404)

    def test_changing_current_pointer_changes_rendered_version(self):
        self._create_version(1, "version-one")
        self._create_version(2, "version-two")
        self._set_current(1)
        first_response = self.service.render_homepage(self.request, self.site)
        self._set_current(2)
        second_response = self.service.render_homepage(self.request, self.site)

        self.assertIn("version-one homepage", first_response.content.decode())
        self.assertIn("version-two homepage", second_response.content.decode())

    def test_missing_published_files_raise_404(self):
        self._set_current(1)
        with self.assertRaises(Http404):
            self.service.get_context(self.site)

        self._write_json(
            f"published/sonder-{self.site.id}/versions/1/manifest.json",
            {
                "version": 1,
                "files": {
                    "header": "header.json",
                    "footer": "footer.json",
                    "pages": {"home": "pages/home.json"},
                },
            },
        )
        self._write_json(
            f"published/sonder-{self.site.id}/versions/1/header.json",
            {"html": "<header>header</header>"},
        )
        self._write_json(
            f"published/sonder-{self.site.id}/versions/1/footer.json",
            {"html": "<footer>footer</footer>"},
        )
        with self.assertRaises(Http404):
            self.service.get_context(self.site)

    def test_invalid_current_version_raises_404(self):
        self._write_json(
            f"published/sonder-{self.site.id}/current.json",
            {"version": "latest"},
        )
        with self.assertRaises(Http404):
            self.service.get_context(self.site)

    def test_malformed_published_json_raises_404(self):
        self._set_current(1)
        self._write(
            f"published/sonder-{self.site.id}/versions/1/manifest.json",
            "{not valid json}",
        )
        with self.assertRaises(Http404):
            self.service.get_context(self.site)
