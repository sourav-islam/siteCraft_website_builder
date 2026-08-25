from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils.text import slugify

from apps.audit.models import AuditLog
from apps.pages.models import Page
from apps.pages.serializers import PageSerializer
from apps.pages.services import PageService
from apps.sites.models import Site

User = get_user_model()


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
        duplicate = Page(site=self.site, title="Home2", slug="home")
        with self.assertRaises(IntegrityError):
            duplicate.save()


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
        page = Page(site=self.site, title="Second", slug="s")
        serializer = PageSerializer(
            instance=page,
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
        self.assertEqual(
            AuditLog.objects.filter(action=AuditLog.Action.CREATED).count(),
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
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.UPDATED).exists(),
        )
