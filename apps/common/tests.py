from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.exceptions import APIException

from apps.common.exceptions import BadRequest, PublishValidationError, ResourceNotFound
from apps.common.permissions import CanDelete, HasUpdate, IsOwner
from apps.common.services import LockService, _serialize_locker
from apps.common.validators import (
    validate_css_file_extension,
    validate_file_size,
    validate_html_file_extension,
)

User = get_user_model()


class CustomExceptionTests(TestCase):
    def test_resource_not_found_is_404(self):
        exc = ResourceNotFound()
        self.assertEqual(exc.status_code, 404)
        self.assertEqual(exc.get_codes(), "resource_not_found")
        self.assertTrue(issubclass(ResourceNotFound, APIException))

    def test_bad_request_is_400(self):
        exc = BadRequest()
        self.assertEqual(exc.status_code, 400)
        self.assertEqual(exc.default_code, "bad_request")

    def test_publish_validation_error_is_plain_exception(self):
        with self.assertRaises(PublishValidationError):
            raise PublishValidationError("bad publish")


class ValidateFileSizeTests(TestCase):
    def test_small_file_passes(self):
        tiny = SimpleUploadedFile("small.html", b"x" * 100)
        validate_file_size(tiny, max_size_mb=1)  # should not raise

    def test_large_file_raises(self):
        huge = SimpleUploadedFile("big.bin", b"x" * (6 * 1024 * 1024))
        with self.assertRaises(ValidationError):
            validate_file_size(huge, max_size_mb=5)


class ValidateHtmlFileExtensionTests(TestCase):
    def test_html_extension_passes(self):
        f = SimpleUploadedFile("page.html", b"<h1></h1>")
        validate_html_file_extension(f)

    def test_htm_extension_passes(self):
        f = SimpleUploadedFile("page.htm", b"<h1></h1>")
        validate_html_file_extension(f)

    def test_case_insensitive_extension(self):
        f = SimpleUploadedFile("page.HTML", b"x")
        validate_html_file_extension(f)

    def test_wrong_extension_raises(self):
        f = SimpleUploadedFile("page.txt", b"x")
        with self.assertRaises(ValidationError):
            validate_html_file_extension(f)


class ValidateCssFileExtensionTests(TestCase):
    def test_css_extension_passes(self):
        f = SimpleUploadedFile("style.css", b"body{}")
        validate_css_file_extension(f)

    def test_other_extension_raises(self):
        f = SimpleUploadedFile("style.scss", b"body{}")
        with self.assertRaises(ValidationError):
            validate_css_file_extension(f)


class FakeRedis:
    """In-memory Redis stand-in that mimics the subset of redis-py API used by LockService."""

    def __init__(self):
        self._store = {}

    def set(self, name, value, ex=None, nx=False):
        if nx and name in self._store:
            return False
        self._store[name] = {"value": value, "ttl": ex}
        return True

    def get(self, name):
        if name not in self._store:
            return None
        return self._store[name]["value"]

    def delete(self, name):
        self._store.pop(name, None)

    def ttl(self, name):
        if name not in self._store:
            return -2
        return self._store[name]["ttl"] or -1

    def expire(self, name, ttl):
        if name in self._store:
            self._store[name]["ttl"] = ttl


class SerializeLockerTests(TestCase):
    def test_serialize_locker_none_returns_none(self):
        self.assertIsNone(_serialize_locker(None))

    def test_serialize_locker_returns_dict(self):
        u = User.objects.create_user(
            username="slock",
            email="slock@example.com",
            password="password",
        )
        data = _serialize_locker(u)
        self.assertEqual(
            data,
            {"id": u.id, "username": "slock", "email": "slock@example.com"},
        )


class LockServiceTests(TestCase):
    def setUp(self):
        self.redis_patcher = mock.patch(
            "apps.common.services.redis_client",
            new_callable=lambda: FakeRedis(),
        )
        self.fake_redis = self.redis_patcher.start()
        self.u1 = User.objects.create_user(
            username="locker1",
            email="u1@example.com",
            password="password",
        )
        self.u2 = User.objects.create_user(
            username="locker2",
            email="u2@example.com",
            password="password",
        )

    def tearDown(self):
        self.redis_patcher.stop()

    def test_lock_key_generation(self):
        key = LockService.get_lock_key("site", 42)
        self.assertEqual(key, "lock:site:42")

    def test_acquire_lock_success_starts_free_lock(self):
        result = LockService.acquire_lock("site", 1, self.u1.id)
        self.assertTrue(result["success"])
        self.assertTrue(result["locked"])
        self.assertEqual(result["locker"]["username"], "locker1")
        self.assertIsNotNone(result.get("ttl_seconds"))

    def test_acquire_lock_rejects_second_user(self):
        LockService.acquire_lock("site", 1, self.u1.id)
        result = LockService.acquire_lock("site", 1, self.u2.id)
        self.assertFalse(result["success"])
        self.assertTrue(result["locked"])
        self.assertEqual(result["locker"]["username"], "locker1")

    def test_acquire_lock_returns_serialized_none_locker_when_user_deleted(self):
        LockService.acquire_lock("page", 5, 9_999_999)
        status = LockService.get_lock_status("page", 5)
        self.assertTrue(status["locked"])
        self.assertIsNone(status["locker"])

    def test_release_lock_success(self):
        LockService.acquire_lock("site", 7, self.u1.id)
        release = LockService.release_lock("site", 7, self.u1.id)
        self.assertTrue(release["success"])
        self.assertFalse(release["locked"])
        self.assertEqual(release["reason"], "released")
        # Now another user can acquire it
        next_result = LockService.acquire_lock("site", 7, self.u2.id)
        self.assertTrue(next_result["success"])

    def test_release_lock_no_lock_gives_404_reason(self):
        release = LockService.release_lock("site", 99, self.u1.id)
        self.assertFalse(release["success"])
        self.assertEqual(release["reason"], "no_lock")

    def test_release_lock_wrong_owner_is_403_reason(self):
        LockService.acquire_lock("site", 1, self.u1.id)
        release = LockService.release_lock("site", 1, self.u2.id)
        self.assertFalse(release["success"])
        self.assertEqual(release["reason"], "not_owner")

    def test_get_lock_status_reports_free(self):
        status = LockService.get_lock_status("site", 3)
        self.assertFalse(status["locked"])
        self.assertIsNone(status["locker"])

    def test_heartbeat_success_refreshes_ttl(self):
        LockService.acquire_lock("site", 2, self.u1.id)
        hb = LockService.heartbeat("site", 2, self.u1.id)
        self.assertTrue(hb["success"])
        self.assertIn("refreshed_at", hb)

    def test_heartbeat_no_lock(self):
        hb = LockService.heartbeat("site", 99, self.u1.id)
        self.assertFalse(hb["success"])
        self.assertEqual(hb["reason"], "no_lock")

    def test_heartbeat_wrong_owner(self):
        LockService.acquire_lock("site", 3, self.u1.id)
        hb = LockService.heartbeat("site", 3, self.u2.id)
        self.assertFalse(hb["success"])
        self.assertEqual(hb["reason"], "not_owner")


class PermissionObject:
    """A lightweight test fixture for permission checks."""

    def __init__(self, owner=None):
        self.owner = owner


class PermissionChildObject:
    def __init__(self, site_owner):
        self.site = PermissionObject(owner=site_owner)


class MockRequest:
    def __init__(self, user=None):
        self.user = user


class IsOwnerHasUpdateCanDeleteTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="powner",
            email="powner@example.com",
            password="password",
        )
        self.other = User.objects.create_user(
            username="pother",
            email="pother@example.com",
            password="password",
        )

    def test_is_owner_true_when_site_owner(self):
        request = MockRequest(user=self.owner)
        obj = PermissionChildObject(site_owner=self.owner)
        self.assertTrue(IsOwner().has_object_permission(request, None, obj))

    def test_is_owner_false_for_other_user(self):
        request = MockRequest(user=self.other)
        obj = PermissionChildObject(site_owner=self.owner)
        self.assertFalse(IsOwner().has_object_permission(request, None, obj))

    def test_has_update_object_with_owner_checks_owner(self):
        request = MockRequest(user=self.owner)
        obj_parent = PermissionObject(owner=self.owner)
        self.assertTrue(HasUpdate().has_object_permission(request, None, obj_parent))
        request2 = MockRequest(user=self.other)
        self.assertFalse(HasUpdate().has_object_permission(request2, None, obj_parent))

    def test_has_update_unauthenticated_returns_false(self):
        request = MockRequest(user=None)
        obj = PermissionObject(owner=self.owner)
        self.assertFalse(HasUpdate().has_object_permission(request, None, obj))

    def test_can_delete_site_owner_is_true(self):
        request = MockRequest(user=self.owner)
        obj = PermissionObject(owner=self.owner)
        self.assertTrue(CanDelete().has_object_permission(request, None, obj))

    def test_can_delete_site_requires_authenticated(self):
        request = MockRequest(user=None)
        obj = PermissionObject(owner=self.owner)
        self.assertFalse(CanDelete().has_object_permission(request, None, obj))
