from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

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
