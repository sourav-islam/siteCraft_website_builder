from django.urls import path

from .views import (
    SiteHeartbeatAPIView,
    SiteListCreateAPIView,
    SiteRetrieveUpdateDestroyAPIView,
    SiteLockAPIView,
    SitePublishAPIView,
)


urlpatterns = [
    path(
        "",
        SiteListCreateAPIView.as_view(),
        name="site-list",
    ),
    path(
        "<int:pk>/",
        SiteRetrieveUpdateDestroyAPIView.as_view(),
        name="site-detail",
    ),
    path(
        "<int:pk>/lock/",
        SiteLockAPIView.as_view(),
        name="site-lock",
    ),
    path(
        "<int:pk>/heartbeat/",
        SiteHeartbeatAPIView.as_view(),
        name="site-heartbeat",
    ),
    path(
        "<int:pk>/publish/", 
        SitePublishAPIView.as_view(), 
        name="site-publish"),
]
