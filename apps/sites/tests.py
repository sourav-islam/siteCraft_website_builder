import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.http import Http404
from django.test import TestCase, override_settings
from django.test.client import RequestFactory
from rest_framework.test import APIClient

from apps.common.exceptions import PublishValidationError
from apps.pages.models import Page
from apps.sites.models import Site, SiteVersion
from apps.sites.services.publish_service import PublishService
from apps.sites.services.render_service import PublishedSiteRenderService


class PublishAndRollbackTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override_media = override_settings(MEDIA_ROOT=self.media_root)
        self.override_media.enable()

        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="password",
        )
        self.other_user = user_model.objects.create_user(
            username="other",
            email="other@example.com",
            password="password",
        )
        self.site = self._create_site("Food House", self.owner)
        self.page = self._create_page(self.site, "Home", "home")
        self.service = PublishService()

    def tearDown(self):
        self.override_media.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _upload(self, name, content):
        return SimpleUploadedFile(name, content.encode("utf-8"))

    def _create_site(self, name, owner):
        site = Site.objects.create(
            owner=owner,
            name=name,
            header=self._upload("header.html", "<header>Header</header>"),
            footer=self._upload("footer.html", "<footer>Footer</footer>"),
            global_css=self._upload("global.css", "body { color: black; }"),
        )
        return site

    def _create_page(self, site, title, slug):
        return Page.objects.create(
            site=site,
            title=title,
            slug=slug,
            html_file=self._upload(f"{slug}.html", f"<main>{title}</main>"),
        )

    def test_publish_creates_immutable_versions_and_current_pointer(self):
        first = self.service.publish(self.site, actor=self.owner)
        first_root = self.service._version_root(self.site, first["version"])

        second = self.service.publish(self.site, actor=self.owner)
        second_root = self.service._version_root(self.site, second["version"])

        self.assertEqual(first["version"], 1)
        self.assertEqual(second["version"], 2)
        self.assertEqual(SiteVersion.objects.filter(site=self.site).count(), 2)
        self.assertTrue(default_storage.exists(f"{first_root}/manifest.json"))
        self.assertTrue(default_storage.exists(f"{second_root}/manifest.json"))

        current_path = f"{self.service._published_root(self.site)}/current.json"
        with open(default_storage.path(current_path)) as current_file:
            self.assertEqual(json.load(current_file), {"version": 2})

        with open(default_storage.path(f"{first_root}/header.json")) as file:
            first_header = file.read()
        self.assertTrue(first_header)

    def test_rollback_updates_pointer_without_deleting_newer_version(self):
        self.service.publish(self.site, actor=self.owner)
        self.service.publish(self.site, actor=self.owner)
        second_root = self.service._version_root(self.site, 2)

        result = self.service.rollback(self.site, 1, actor=self.owner)

        self.assertEqual(result["version"], 1)
        self.assertTrue(default_storage.exists(f"{second_root}/manifest.json"))
        current_path = f"{self.service._published_root(self.site)}/current.json"
        with open(default_storage.path(current_path)) as current_file:
            self.assertEqual(json.load(current_file), {"version": 1})

    def test_rollback_rejects_missing_or_incomplete_version(self):
        with self.assertRaises(PublishValidationError):
            self.service.rollback(self.site, 99, actor=self.owner)

        self.service.publish(self.site, actor=self.owner)
        manifest_path = default_storage.path(
            f"{self.service._version_root(self.site, 1)}/manifest.json"
        )
        with open(manifest_path, "w") as manifest_file:
            json.dump({"version": 1, "files": {"header": "missing.json"}}, manifest_file)

        with self.assertRaises(PublishValidationError):
            self.service.rollback(self.site, 1, actor=self.owner)

    def test_failed_publish_keeps_previous_current_pointer(self):
        self.service.publish(self.site, actor=self.owner)
        current_path = f"{self.service._published_root(self.site)}/current.json"

        with mock.patch.object(
            self.service,
            "_write_page",
            side_effect=RuntimeError("generation failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.service.publish(self.site, actor=self.owner)

        with open(default_storage.path(current_path)) as current_file:
            self.assertEqual(json.load(current_file), {"version": 1})
        self.assertEqual(SiteVersion.objects.filter(site=self.site).count(), 1)

    def test_other_user_cannot_publish_or_rollback_site(self):
        client = APIClient()
        client.force_authenticate(user=self.other_user)

        publish_response = client.post(f"/api/v1/sites/{self.site.id}/publish")
        rollback_response = client.post(
            f"/api/v1/sites/{self.site.id}/rollback",
            {"version": 1},
            format="json",
        )

        self.assertEqual(publish_response.status_code, 403)
        self.assertEqual(rollback_response.status_code, 403)

    def test_first_version_is_independent_per_site(self):
        other_site = self._create_site("Pixel Agency", self.owner)
        self._create_page(other_site, "Home", "home")

        first = self.service.publish(self.site, actor=self.owner)
        other_first = self.service.publish(other_site, actor=self.owner)

        self.assertEqual(first["version"], 1)
        self.assertEqual(other_first["version"], 1)


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
        self.request = RequestFactory().get("/api/v1/sites/1/published")

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

        response = self.client.get(
            f"/api/v1/sites/{self.site.id}/published"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "version-one homepage")

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

        self._write_json(
            f"published/sonder-{self.site.id}/versions/1/manifest.json",
            {"version": 1, "files": {}},
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
