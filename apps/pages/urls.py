from django.urls import path

from .views import (
    PageHeartbeatAPIView,
    PageListCreateAPIView,
    PageRetrieveUpdateDestroyAPIView,
    PageLockAPIView,
)


urlpatterns = [
    path(
        "",
        PageListCreateAPIView.as_view(),
        name="page-list",
    ),
    path(
        "<int:pk>/",
        PageRetrieveUpdateDestroyAPIView.as_view(),
        name="page-detail",
    ),
    path(
        "<int:pk>/lock/",
        PageLockAPIView.as_view(),
        name="page-lock",
    ),
    path(
        "<int:pk>/heartbeat/",
        PageHeartbeatAPIView.as_view(),
        name="page-heartbeat",
    ),
]
