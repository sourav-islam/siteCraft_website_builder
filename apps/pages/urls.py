from django.urls import path

from .views import (
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
]
