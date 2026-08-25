import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditLog
from apps.common.services import LockService
from apps.pages.models import Page
from apps.sites.models import Site
from apps.sites.services.site_service import SiteService

from .test_helpers import SiteApiBase


class SiteListCreateAPITests(SiteApiBase):
    def test_create_site_success(self):
        response = self.client.post(
            self._list_url(),
            {"name": "Created Site", "description": "d"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Site.objects.count(), 1)
        site = Site.objects.first()
        self.assertEqual(site.owner, self.owner)
        self.assertEqual(site.created_by, self.owner)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.CREATED,
                object_id=site.id,
            ).exists(),
        )

    def test_list_returns_owned_sites(self):
        SiteService.create_site(owner=self.owner, actor=self.owner, name="Mine")
        SiteService.create_site(owner=self.other, actor=self.other, name="Yours")
        response = self.client.get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Mine")

    def test_list_unauthenticated_401(self):
        self.client.logout()
        response = self.client.get(self._list_url())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_search_and_ordering(self):
        SiteService.create_site(owner=self.owner, actor=self.owner, name="Banana")
        SiteService.create_site(owner=self.owner, actor=self.owner, name="Apple")
        response = self.client.get(self._list_url(), {"search": "Apple"})
        self.assertEqual(len(response.data), 1)
        ordered = self.client.get(self._list_url(), {"ordering": "name"})
        names = [site["name"] for site in ordered.data]
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
        response = self.client.get(self._detail_url(self.site))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Original")

    def test_retrieve_other_owner_forbidden(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.get(self._detail_url(self.site))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_site_records_audit_log(self):
        response = self.client.patch(
            self._detail_url(self.site),
            {"name": "Changed"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.site.refresh_from_db()
        self.assertEqual(self.site.name, "Changed")
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.UPDATED).exists(),
        )

    def test_update_blocked_when_locked_by_other(self):
        LockService.acquire_lock("site", self.site.id, self.other.id)
        response = self.client.patch(
            self._detail_url(self.site),
            {"name": "Blocked"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "site_locked")

    def test_destroy_blocked_when_locked(self):
        LockService.acquire_lock("site", self.site.id, self.other.id)
        response = self.client.delete(self._detail_url(self.site))
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_destroy_success_and_audit_log_delete(self):
        site_id = self.site.id
        response = self.client.delete(self._detail_url(self.site))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
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
        response = self.client.get(self._lock_url(self.site))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["lock"]["locked"])

    def test_acquire_lock(self):
        response = self.client.post(self._lock_url(self.site))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["lock"]["locked"])
        response = self.client.post(self._lock_url(self.site))
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_other_user_release_is_403(self):
        self.client.post(self._lock_url(self.site))
        self.client.force_authenticate(user=self.other)
        response = self.client.delete(self._lock_url(self.site))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_release_lock_when_missing_is_404(self):
        response = self.client.delete(self._lock_url(self.site))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_heartbeat_after_acquire_is_ok(self):
        self.client.post(self._lock_url(self.site))
        response = self.client.post(self._heartbeat_url(self.site))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("refreshed_at", response.data["lock"])

    def test_heartbeat_without_lock_is_404(self):
        response = self.client.post(self._heartbeat_url(self.site))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PublishApiTests(SiteApiBase):
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
        Page.objects.create(
            site=self.site,
            title="H",
            slug="home",
            html_file=SimpleUploadedFile("h.html", b"<main/>"),
        )

    def tearDown(self):
        self.override_media.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_publish_api_success(self):
        response = self.client.post(
            reverse("site-publish", kwargs={"pk": self.site.pk}),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["version"], 1)
        self.assertEqual(self.site.versions.count(), 1)

    def test_rollback_api_missing_version_is_400(self):
        response = self.client.post(
            reverse("site-rollback", kwargs={"pk": self.site.pk}),
            {"version": 99},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publish_api_blocked_by_lock(self):
        self.client.force_authenticate(user=self.other)
        LockService.acquire_lock("site", self.site.id, self.other.id)
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(
            reverse("site-publish", kwargs={"pk": self.site.pk}),
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
