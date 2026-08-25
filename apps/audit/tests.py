from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services import (
    AuditService,
    compute_hash,
    diff_fields,
    normalize_value,
)
from apps.pages.models import Page
from apps.sites.models import Site

User = get_user_model()


class ComputeHashTests(TestCase):
    def test_hash_none_and_empty_string(self):
        self.assertEqual(compute_hash(None), "(empty)")
        self.assertEqual(compute_hash(""), "(empty)")

    def test_hash_string_consistent(self):
        h1 = compute_hash("hello world")
        h2 = compute_hash("hello world")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, compute_hash("different"))

    def test_hash_bytes(self):
        h1 = compute_hash(b"hello")
        self.assertIsInstance(h1, str)
        self.assertTrue(len(h1) == 64)

    def test_hash_file_object(self):
        file_obj = ContentFile(b"content", name="test.html")
        result = compute_hash(file_obj)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) == 64 or result.startswith("("))

    def test_hash_falls_back_to_str_for_other_types(self):
        class Dummy:
            def __str__(self):
                return "dummy"

        result = compute_hash(Dummy())
        self.assertIsInstance(result, str)


class NormalizeValueTests(TestCase):
    def test_normalize_none_and_empty(self):
        self.assertEqual(normalize_value(None), "(empty)")
        self.assertEqual(normalize_value(""), "(empty)")

    def test_normalize_file_with_name(self):
        file_obj = ContentFile(b"<h1/>", name="header.html")
        self.assertEqual(normalize_value(file_obj), "header.html")

    def test_normalize_file_without_name(self):
        file_obj = ContentFile(b"<h1/>")
        file_obj.name = ""
        self.assertEqual(normalize_value(file_obj), "(empty)")

    def test_normalize_string_returns_str(self):
        self.assertEqual(normalize_value(42), "42")
        self.assertEqual(normalize_value("hello"), "hello")


class DiffFieldsTests(TestCase):
    def test_diff_fields_detects_change(self):
        owner = User.objects.create_user(username="x", email="x@e.com", password="p")
        site = Site.objects.create(owner=owner, name="Old Name")
        changes = diff_fields(site, {"name": "New Name"})
        self.assertIn("name", changes)
        self.assertEqual(changes["name"]["old"], "Old Name")
        self.assertEqual(changes["name"]["new"], "New Name")

    def test_diff_fields_no_change(self):
        owner = User.objects.create_user(username="y", email="y@e.com", password="p")
        site = Site.objects.create(owner=owner, name="Name")
        changes = diff_fields(site, {"name": "Name"})
        self.assertEqual(changes, {})

    def test_diff_fields_file_content_change(self):
        owner = User.objects.create_user(username="z", email="z@e.com", password="p")
        page = Page.objects.create(
            site=Site.objects.create(owner=owner, name="Site"),
            title="T",
            slug="t",
            html_file=ContentFile(b"<h1/>", name="old.html"),
        )
        new_file = ContentFile(b"<h1>changed</h1>", name="new.html")
        changes = diff_fields(page, {"html_file": new_file})
        self.assertIn("html_file", changes)


class AuditServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner_audit",
            email="owner_audit@example.com",
            password="password",
        )
        self.actor = User.objects.create_user(
            username="actor_audit",
            email="actor_audit@example.com",
            password="password",
        )

    def test_log_create_creates_row(self):
        site = Site.objects.create(owner=self.owner, name="Audit Site")
        AuditService.log_create(site, self.actor)
        log = AuditLog.objects.get(
            content_type=ContentType.objects.get_for_model(Site),
            object_id=site.pk,
            action=AuditLog.Action.CREATED,
        )
        self.assertEqual(log.actor, self.actor)

    def test_log_update_returns_none_without_changes(self):
        site = Site.objects.create(owner=self.owner, name="S")
        result = AuditService.log_update(site, self.actor, {})
        self.assertIsNone(result)
        self.assertFalse(
            AuditLog.objects.filter(action=AuditLog.Action.UPDATED).exists(),
        )

    def test_log_update_with_changes(self):
        site = Site.objects.create(owner=self.owner, name="Before")
        changes = diff_fields(site, {"name": "After"})
        AuditService.log_update(site, self.actor, changes)
        log = AuditLog.objects.get(action=AuditLog.Action.UPDATED)
        self.assertEqual(log.changes["name"]["old"], "Before")
        self.assertEqual(log.changes["name"]["new"], "After")

    def test_log_delete_stores_metadata(self):
        site = Site.objects.create(owner=self.owner, name="Gone")
        AuditService.log_delete(site, self.actor, metadata={"name": "Gone"})
        log = AuditLog.objects.get(action=AuditLog.Action.DELETED)
        self.assertEqual(log.metadata["name"], "Gone")
        site.delete()
        # log row still exists because object_id is int
        self.assertTrue(AuditLog.objects.filter(pk=log.pk).exists())

    def test_log_action_generic(self):
        site = Site.objects.create(owner=self.owner, name="A")
        AuditService.log_action(
            site,
            self.actor,
            AuditLog.Action.PUBLISHED,
            metadata={"version": 1},
        )
        log = AuditLog.objects.get(action=AuditLog.Action.PUBLISHED)
        self.assertEqual(log.metadata["version"], 1)

    def test_next_html_file_version_sequence(self):
        owner = self.owner
        site = Site.objects.create(owner=owner, name="VV")
        ct = ContentType.objects.get_for_model(Site)
        v1 = AuditService._next_html_file_version(ct, site.pk)
        self.assertEqual(v1, 1)
        AuditLog.objects.create(
            content_type=ct,
            object_id=site.pk,
            action=AuditLog.Action.UPDATED,
            metadata={"html_file_version": 1},
        )
        self.assertEqual(AuditService._next_html_file_version(ct, site.pk), 2)
        AuditLog.objects.create(
            content_type=ct,
            object_id=site.pk,
            action=AuditLog.Action.UPDATED,
            metadata={"html_file_version": "bad"},
        )
        # falls back to 1 on parse error
        self.assertEqual(AuditService._next_html_file_version(ct, site.pk), 1)


class AuditLogModelTests(TestCase):
    def test_audit_log_str(self):
        owner = User.objects.create_user(username="m", email="m@e.com", password="p")
        site = Site.objects.create(owner=owner, name="S")
        AuditService.log_create(site, owner)
        log = AuditLog.objects.first()
        expected = f"created on {ContentType.objects.get_for_model(Site)}#{site.pk}"
        self.assertEqual(str(log), expected)


class SiteAuditLogListAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="audit_api",
            email="audit_api@example.com",
            password="password",
        )
        self.other = User.objects.create_user(
            username="other_api",
            email="other_api@example.com",
            password="password",
        )
        self.site = Site.objects.create(owner=self.owner, name="Audit API Site")
        self.url = reverse("site-audit-log", kwargs={"site_id": self.site.pk})

    def test_audit_log_unauthenticated(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_audit_log_other_user_forbidden(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_audit_log_owner_views_list(self):
        AuditService.log_create(self.site, self.owner)
        AuditService.log_update(self.site, self.owner, {"name": {"old": "a", "new": "b"}})
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)
        # actor_username is serialized
        self.assertEqual(response.data["results"][0]["actor_username"], self.owner.username)
