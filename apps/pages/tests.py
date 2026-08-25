from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils.text import slugify
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.common.services import LockService
from apps.pages.models import Page
from apps.pages.serializers import PageSerializer
from apps.pages.services import PageService
from apps.sites.models import Site

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


class PageModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="pmodel",
            email="pmodel@example.com",
            password="password",
        )
        self.site = Site.objects.create(owner=self.owner, name="ModelSite")

    def test_str_contains_site_and_title(self):
        page = Page.objects.create(
            site=self.site,
            title="About",
            slug="about",
        )
        self.assertIn("ModelSite", str(page))
        self.assertIn("About", str(page))

    def test_save_generates_slug_from_title_if_missing(self):
        page = Page.objects.create(site=self.site, title="My Great Page")
        self.assertEqual(page.slug, slugify("My Great Page"))

    def test_unique_slug_per_site(self):
        Page.objects.create(site=self.site, title="Home", slug="home")
        second = Page(site=self.site, title="Home2")
        second.slug = "home"  # force duplicate
        with self.assertRaises(IntegrityError):
            second.save()


class PageSerializerValidationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="pval",
            email="pval@example.com",
            password="password",
        )
        self.site = Site.objects.create(owner=self.owner, name="ValSite")
        Page.objects.create(site=self.site, title="H", slug="h", is_homepage=True)

    def test_serializer_blocks_two_homepages(self):
        page2 = Page(site=self.site, title="Second", slug="s")
        serializer = PageSerializer(
            instance=page2,
            data={"title": "Second", "slug": "s", "is_homepage": True},
            context={"site": self.site},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("is_homepage", serializer.errors)

    def test_serializer_allows_updating_own_homepage(self):
        existing = Page.objects.get(slug="h")
        serializer = PageSerializer(
            instance=existing,
            data={"title": "Home Updated", "slug": "h", "is_homepage": True},
            context={"site": self.site},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


class PageServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="psvc",
            email="psvc@example.com",
            password="password",
        )
        self.site = Site.objects.create(owner=self.owner, name="SvcSite")

    def test_create_page_generates_unique_slug(self):
        first = PageService.create_page(
            site=self.site,
            title="About",
            created_by=self.owner,
            updated_by=self.owner,
        )
        second = PageService.create_page(
            site=self.site,
            title="About",
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.assertEqual(first.slug, "about")
        self.assertEqual(second.slug, "about-1")
        # Audit log rows created for both
        self.assertEqual(
            AuditLog.objects.filter(
                action=AuditLog.Action.CREATED,
            ).count(),
            2,
        )

    def test_update_page_writes_audit_log_on_change(self):
        page = PageService.create_page(
            site=self.site,
            title="Alpha",
            created_by=self.owner,
            updated_by=self.owner,
        )
        PageService.update_page(page, title="Beta", updated_by=self.owner)
        page.refresh_from_db()
        self.assertEqual(page.title, "Beta")
        update_logs = AuditLog.objects.filter(action=AuditLog.Action.UPDATED)
        self.assertTrue(update_logs.exists())


class PageApiBase(TestCase):
    """Shared setup for API tests."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="papi",
            email="papi@example.com",
            password="password",
        )
        self.other = User.objects.create_user(
            username="papi_other",
            email="papi_other@example.com",
            password="password",
        )
        self.site = Site.objects.create(owner=self.owner, name="APISite")
        self.other_site = Site.objects.create(owner=self.other, name="OtherSite")
        self.redis_patcher = mock.patch(
            "apps.common.services.redis_client",
            new_callable=lambda: FakeRedis(),
        )
        self.redis_patcher.start()
        self.client.force_authenticate(user=self.owner)

    def tearDown(self):
        self.redis_patcher.stop()

    def _list_url(self, site=None):
        return reverse("page-list", kwargs={"site_id": (site or self.site).pk})

    def _detail_url(self, page):
        return reverse(
            "page-detail",
            kwargs={"site_id": page.site_id, "pk": page.pk},
        )

    def _lock_url(self, page):
        return reverse(
            "page-lock",
            kwargs={"site_id": page.site_id, "pk": page.pk},
        )

    def _heartbeat_url(self, page):
        return reverse(
            "page-heartbeat",
            kwargs={"site_id": page.site_id, "pk": page.pk},
        )


class PageListCreateAPITests(PageApiBase):
    def test_create_page_success(self):
        payload = {"title": "Services", "slug": "services"}
        response = self.client.post(self._list_url(), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Page.objects.filter(site=self.site).count(), 1)
        self.assertEqual(Page.objects.first().created_by, self.owner)

    def test_list_returns_only_pages_for_url_site(self):
        PageService.create_page(
            site=self.site,
            title="P1",
            created_by=self.owner,
            updated_by=self.owner,
        )
        PageService.create_page(
            site=self.other_site,
            title="OtherPage",
            created_by=self.other,
            updated_by=self.other,
        )
        res = self.client.get(self._list_url())
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["title"], "P1")

    def test_create_requires_authentication(self):
        self.client.logout()
        res = self.client.post(self._list_url(), {"title": "X"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_404_when_wrong_owner_creates_under_other_site(self):
        self.client.force_authenticate(user=self.other)
        res = self.client.post(
            self._list_url(self.site),
            {"title": "Hacked"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class PageRetrieveUpdateDestroyAPITests(PageApiBase):
    def setUp(self):
        super().setUp()
        self.page = PageService.create_page(
            site=self.site,
            title="Home",
            created_by=self.owner,
            updated_by=self.owner,
        )

    def test_retrieve_page(self):
        res = self.client.get(self._detail_url(self.page))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["title"], "Home")

    def test_other_user_cannot_update(self):
        self.client.force_authenticate(user=self.other)
        res = self.client.patch(
            self._detail_url(self.page),
            {"title": "Wrong"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_success(self):
        res = self.client.patch(
            self._detail_url(self.page),
            {"title": "Updated", "meta_description": "SEO"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.page.refresh_from_db()
        self.assertEqual(self.page.title, "Updated")

    def test_update_blocked_when_locked_by_other(self):
        LockService.acquire_lock("page", self.page.id, self.other.id)
        res = self.client.patch(
            self._detail_url(self.page),
            {"title": "Blocked"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], "page_locked")

    def test_destroy_blocked_when_locked(self):
        LockService.acquire_lock("page", self.page.id, self.other.id)
        res = self.client.delete(self._detail_url(self.page))
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_destroy_success_creates_audit_log(self):
        res = self.client.delete(self._detail_url(self.page))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Page.objects.filter(pk=self.page.pk).exists())
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.DELETED,
                object_id=self.page.id,
            ).exists(),
        )


class PageLockAndHeartbeatAPITests(PageApiBase):
    def setUp(self):
        super().setUp()
        self.page = PageService.create_page(
            site=self.site,
            title="LPage",
            created_by=self.owner,
            updated_by=self.owner,
        )

    def test_get_lock_status_free(self):
        res = self.client.get(self._lock_url(self.page))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["lock"]["locked"])

    def test_acquire_lock_and_release(self):
        res = self.client.post(self._lock_url(self.page))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["lock"]["locked"])

        release = self.client.delete(self._lock_url(self.page))
        self.assertEqual(release.status_code, status.HTTP_200_OK)
        self.assertFalse(release.data["lock"]["locked"])

    def test_release_nonexistent_lock_is_404(self):
        res = self.client.delete(self._lock_url(self.page))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_heartbeat_no_lock_is_404(self):
        res = self.client.post(self._heartbeat_url(self.page))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_heartbeat_success_after_acquire(self):
        self.client.post(self._lock_url(self.page))
        res = self.client.post(self._heartbeat_url(self.page))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("refreshed_at", res.data["lock"])
