from rest_framework import filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsOwner

from .models import Site
from .serializers import SiteSerializer
from .services import SiteService


class SiteViewSet(ModelViewSet):

    serializer_class = SiteSerializer

    permission_classes = [
        IsAuthenticated,
        IsOwner,
    ]

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    search_fields = [
        "name",
        "description",
    ]

    ordering_fields = [
        "name",
        "created_at",
    ]

    ordering = [
        "-created_at",
    ]

    def get_queryset(self):
        return Site.objects.filter(
            owner=self.request.user
        )

    def perform_create(self, serializer):
        SiteService.create_site(
            owner=self.request.user,
            **serializer.validated_data,
        )