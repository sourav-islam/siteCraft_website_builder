import json
from pathlib import Path
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.http import Http404
from django.test import TestCase, override_settings
from django.test.client import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.common.exceptions import PublishValidationError
from apps.common.services import LockService
from apps.pages.models import Page
from apps.sites.models import Site, SiteVersion
from apps.sites.serializers import SiteRollbackSerializer
from apps.sites.services.publish_service import PublishService
from apps.sites.services.render_service import PublishedSiteRenderService
from apps.sites.services.site_service import SiteService

User = get_user_model()


class FakeRedis:
    def __init__(self):
        self._store = {}

    def set(self, name, value, ex=None, nx=False):
        if nx and name in self._store:
            return False
        self._store[name] = {"value": value, "ttl": ex}
        return True

    def get(self, name):
        return self._store[name]["value"] if name in self._store else None

    def delete(self, name):
        self._store.pop(name, None)

    def ttl(self, name):
        return self._store[name]["ttl"] if name in self._store else -2

    def expire(self, name, ttl):
        if name in self._store:
            self._store[name]["ttl"] = ttl


class SiteModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="smo",
            email="smo@example.com",
            password="password",
        )

    def test_str_returns_name(self):
        site = Site.objects.create(owner=self.owner, name="My Website")
        self.assertEqual(str(site), "My Website")

    def test_status_default_is_draft(self):
        site = Site.objects.create(owner=self.owner, name="D")
        self.assertEqual(site.status, Site.Status.DRAFT)

    def test_is_public_default_false(self):
        site = Site.objects.create(owner=self.owner, name="P")
        self.assertFalse(site.is_public)


class SiteVersionModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="svc",
            email="svc@example.com",
            password="password",
        )
        self.site = Site.objects.create(owner=self.owner, name="V")

    def test_unique_constraint_per_site_version(self):
        SiteVersion.objects.create(site=self.site, version_number=1)
        duplicate = SiteVersion(site=self.site, version_number=1)
        with self.assertRaises(IntegrityError):
            duplicate.save()

    def test_str_includes_name_and_version(self):
        v = SiteVersion.objects.create(site=self.site, version_number=3)
        self.assertIn("V", str(v))
        self.assertIn("Version 3", str(v))


class SiteRollbackSerializerTests(TestCase):
    def test_version_must_be_positive(self):
        serializer = SiteRollbackSerializer(data={"version": 0})
        self.assertFalse(serializer.is_valid())
        serializer2 = SiteRollbackSerializer(data={"version": 1})
        self.assertTrue(serializer2.is_valid())


class SiteServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="ssvc",
            email="ssvc@example.com",
            password="password",
        )

    def test_create_site_creates_audit_row(self):
        site = SiteService.create_site(owner=self.owner, name="Created", actor=self.owner)
        self.assertEqual(site.name, "Created")
        self.assertEqual(
            AuditLog.objects.filter(action=AuditLog.Action.CREATED).count(),
            1,
        )

    def test_update_site_records_changes_and_saves(self):
        site = SiteService.create_site(owner=self.owner, name="Before")
        SiteService.update_site(site, name="After", actor=self.owner)
        site.refresh_from_db()
        self.assertEqual(site.name, "After")
        log = AuditLog.objects.get(action=AuditLog.Action.UPDATED)
        self.assertIn("name", log.changes)


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

    def test_validate_readiness_requires_header_footer(self):
        empty_site = Site.objects.create(owner=self.owner, name="Empty")
        with self.assertRaises(PublishValidationError):
            self.service._validate_readiness(empty_site, [])

    def test_validate_readiness_requires_pages(self):
        header_only = self._create_site("HdrSite", self.owner)
        with self.assertRaises(PublishValidationError):
            self.service._validate_readiness(header_only, [])

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
            f"{self.service._version_root(self.site, 1)}/manifest.json",
        )
        with open(manifest_path, "w") as manifest_file:
            json.dump({"version": 1, "files": {"header": "missing.json"}}, manifest_file)

        with self.assertRaises(PublishValidationError):
            self.service.rollback(self.site, 1, actor=self.owner)

    def test_failed_publish_keeps_previous_current_pointer(self):
        self.service.publish(self.site, actor=self.owner)
        current_path = f"{self.service._published_root(self.site)}/current.json"

        with (
            mock.patch.object(
                self.service,
                "_write_page",
                side_effect=RuntimeError("generation failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
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
            f"/sites/{self.site.id}/published/",
        )

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

        response = self.client.get(
            f"/sites/{self.site.id}/published/about",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "About page content")
        self.assertNotContains(response, "version-one homepage")

    def test_unknown_published_page_slug_returns_404(self):
        self._create_version(1, "version-one")
        self._set_current(1)

        response = self.client.get(
            f"/sites/{self.site.id}/published/missing",
        )

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


class SiteApiBase(TestCase):
    """Shared setup for Sites API tests."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="sapi",
            email="sapi@example.com",
            password="password",
        )
        self.other = User.objects.create_user(
            username="sapi_other",
            email="sapi_other@example.com",
            password="password",
        )
        self.redis_patcher = mock.patch(
            "apps.common.services.redis_client",
            new_callable=lambda: FakeRedis(),
        )
        self.redis_patcher.start()
        self.client.force_authenticate(user=self.owner)

    def tearDown(self):
        self.redis_patcher.stop()

    def _list_url(self):
        return reverse("site-list")

    def _detail_url(self, site):
        return reverse("site-detail", kwargs={"pk": site.pk})

    def _lock_url(self, site):
        return reverse("site-lock", kwargs={"pk": site.pk})

    def _heartbeat_url(self, site):
        return reverse("site-heartbeat", kwargs={"pk": site.pk})


class SiteListCreateAPITests(SiteApiBase):
    def test_create_site_success(self):
        res = self.client.post(
            self._list_url(),
            {"name": "Created Site", "description": "d"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Site.objects.count(), 1)
        site = Site.objects.first()
        self.assertEqual(site.owner, self.owner)
        self.assertEqual(site.created_by, self.owner)
        # Audit create log exists
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.CREATED,
                object_id=site.id,
            ).exists(),
        )

    def test_list_returns_owned_sites(self):
        SiteService.create_site(owner=self.owner, actor=self.owner, name="Mine")
        SiteService.create_site(owner=self.other, actor=self.other, name="Yours")
        res = self.client.get(self._list_url())
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["name"], "Mine")

    def test_list_unauthenticated_401(self):
        self.client.logout()
        res = self.client.get(self._list_url())
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_search_and_ordering(self):
        SiteService.create_site(owner=self.owner, actor=self.owner, name="Banana")
        SiteService.create_site(owner=self.owner, actor=self.owner, name="Apple")
        res = self.client.get(self._list_url(), {"search": "Apple"})
        self.assertEqual(len(res.data["results"]), 1)
        res_ordered = self.client.get(self._list_url(), {"ordering": "name"})
        names = [s["name"] for s in res_ordered.data["results"]]
        self.assertEqual(names, sorted(names))


class SiteRetrieveUpdateDestroyAPITests(SiteApiBase):
    def setUp(self):
        super().setUp()
        self.site = SiteService.create_site(
            owner=self.owner,
            actor=self.owner,
            name="Original",
            description="orig",
        )

    def test_retrieve_site(self):
        res = self.client.get(self._detail_url(self.site))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["name"], "Original")

    def test_retrieve_other_owner_forbidden(self):
        self.client.force_authenticate(user=self.other)
        res = self.client.get(self._detail_url(self.site))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_site_records_audit_log(self):
        res = self.client.patch(
            self._detail_url(self.site),
            {"name": "Changed"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.site.refresh_from_db()
        self.assertEqual(self.site.name, "Changed")
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.UPDATED).exists(),
        )

    def test_update_blocked_when_locked_by_other(self):
        LockService.acquire_lock("site", self.site.id, self.other.id)
        res = self.client.patch(
            self._detail_url(self.site),
            {"name": "Blocked"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], "site_locked")

    def test_destroy_blocked_when_locked(self):
        LockService.acquire_lock("site", self.site.id, self.other.id)
        res = self.client.delete(self._detail_url(self.site))
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_destroy_success_and_audit_log_delete(self):
        site_id = self.site.id
        res = self.client.delete(self._detail_url(self.site))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Site.objects.filter(pk=site_id).exists())
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.DELETED,
                object_id=site_id,
            ).exists(),
        )


class SiteLockAndHeartbeatAPIViewTests(SiteApiBase):
    def setUp(self):
        super().setUp()
        self.site = SiteService.create_site(
            owner=self.owner,
            actor=self.owner,
            name="Lockable",
        )

    def test_get_lock_status_free(self):
        res = self.client.get(self._lock_url(self.site))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["lock"]["locked"])

    def test_acquire_lock(self):
        res = self.client.post(self._lock_url(self.site))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["lock"]["locked"])
        # Now the same user can't re-acquire
        res2 = self.client.post(self._lock_url(self.site))
        self.assertEqual(res2.status_code, status.HTTP_409_CONFLICT)

    def test_other_user_release_is_403(self):
        self.client.post(self._lock_url(self.site))
        self.client.force_authenticate(user=self.other)
        res = self.client.delete(self._lock_url(self.site))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_release_lock_when_missing_is_404(self):
        res = self.client.delete(self._lock_url(self.site))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_heartbeat_after_acquire_is_ok(self):
        self.client.post(self._lock_url(self.site))
        res = self.client.post(self._heartbeat_url(self.site))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("refreshed_at", res.data["lock"])

    def test_heartbeat_without_lock_is_404(self):
        res = self.client.post(self._heartbeat_url(self.site))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class PublishApiTests(SiteApiBase):
    """Publish and rollback API-level tests."""

    def setUp(self):
        super().setUp()
        self.media_root = tempfile.mkdtemp()
        self.override_media = override_settings(MEDIA_ROOT=self.media_root)
        self.override_media.enable()
        self.site = Site.objects.create(
            owner=self.owner,
            name="PubSite",
            header=SimpleUploadedFile("h.html", b"<header/>"),
            footer=SimpleUploadedFile("f.html", b"<footer/>"),
            global_css=SimpleUploadedFile("g.css", b"body{}"),
        )
        self.page = Page.objects.create(
            site=self.site,
            title="H",
            slug="home",
            html_file=SimpleUploadedFile("h.html", b"<main/>"),
        )

    def tearDown(self):
        self.override_media.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_publish_api_success(self):
        res = self.client.post(
            reverse("site-publish", kwargs={"pk": self.site.pk}),
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["version"], 1)
        self.assertEqual(self.site.versions.count(), 1)

    def test_rollback_api_missing_version_is_400(self):
        res = self.client.post(
            reverse("site-rollback", kwargs={"pk": self.site.pk}),
            {"version": 99},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publish_api_blocked_by_lock(self):
        self.client.force_authenticate(user=self.other)
        LockService.acquire_lock("site", self.site.id, self.other.id)
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            reverse("site-publish", kwargs={"pk": self.site.pk}),
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
