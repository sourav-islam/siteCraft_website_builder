from django.urls import path

from .views import (
    SiteListCreateAPIView,
    SiteRetrieveUpdateDestroyAPIView,
    SiteLockAPIView,
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
]
