from django.test import SimpleTestCase
from django.urls import resolve

from .views import SiteViewSet


class SiteRoutingTests(SimpleTestCase):
    def test_sites_root_resolves_to_site_list_endpoint(self):
        resolver = resolve("/api/sites/")

        self.assertEqual(resolver.view_name, "site-list")
        self.assertEqual(resolver.func.__name__, "SiteViewSet")
