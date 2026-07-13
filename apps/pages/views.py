from rest_framework import filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsOwner

from .models import Page
from .serializers import PageSerializer
from .services import PageService


class PageViewSet(ModelViewSet):
    serializer_class = PageSerializer

    permission_classes = [
        IsAuthenticated,
        IsOwner,
    ]

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    search_fields = [
        "title",
        "slug",
    ]

    ordering_fields = [
        "title",
        "created_at",
    ]

    ordering = [
        "created_at",
    ]

    def get_queryset(self):
        return (
            Page.objects
            .select_related("site")
            .filter(site__owner=self.request.user)
        )

    def perform_create(self, serializer):
        PageService.create_page(
            **serializer.validated_data
        )

    def perform_update(self, serializer):
        PageService.update_page(
            serializer.instance,
            **serializer.validated_data,
        )