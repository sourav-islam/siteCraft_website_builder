from django.urls import include, path

from .views import (
    SiteHeartbeatAPIView,
    SiteListCreateAPIView,
    SiteRetrieveUpdateDestroyAPIView,
    SiteLockAPIView,
    SitePublishAPIView,
    SiteRollbackAPIView,
    PublishedSiteAPIView,
)


urlpatterns = [
    path(
        "",
        SiteListCreateAPIView.as_view(),
        name="site-list",
    ),
    path(
        "/<int:pk>",
        SiteRetrieveUpdateDestroyAPIView.as_view(),
        name="site-detail",
    ),
    path(
        "/<int:pk>/lock",
        SiteLockAPIView.as_view(),
        name="site-lock",
    ),
    path(
        "/<int:pk>/heartbeat",
        SiteHeartbeatAPIView.as_view(),
        name="site-heartbeat",
    ),
    path(
        "/<int:pk>/publish",
        SitePublishAPIView.as_view(),
        name="site-publish",
    ),
    path(
        "/<int:pk>/rollback",
        SiteRollbackAPIView.as_view(),
        name="site-rollback",
    ),
    path(
        "/<int:pk>/published",
        PublishedSiteAPIView.as_view(),
        name="published-site",
    ),
    path("/<int:site_id>/pages", include("apps.pages.urls")),
    # Nested audit-log route (read-only)
    path("/<int:site_id>/audit-log", include("apps.audit.urls")),
]
