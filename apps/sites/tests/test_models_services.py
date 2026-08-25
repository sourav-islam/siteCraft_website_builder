from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.sites.models import Site, SiteVersion
from apps.sites.services.site_service import SiteService

User = get_user_model()


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
        version = SiteVersion.objects.create(site=self.site, version_number=3)
        self.assertIn("V", str(version))
        self.assertIn("Version 3", str(version))


class SiteRollbackSerializerTests(TestCase):
    def test_version_must_be_positive(self):
        from apps.sites.serializers import SiteRollbackSerializer

        serializer = SiteRollbackSerializer(data={"version": 0})
        self.assertFalse(serializer.is_valid())
        serializer = SiteRollbackSerializer(data={"version": 1})
        self.assertTrue(serializer.is_valid())


class SiteServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="ssvc",
            email="ssvc@example.com",
            password="password",
        )

    def test_create_site_creates_audit_row(self):
        site = SiteService.create_site(
            owner=self.owner,
            name="Created",
            actor=self.owner,
        )
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
