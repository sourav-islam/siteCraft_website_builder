from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions

from apps.sites.models import Site

from .models import AuditLog
from .serializers import AuditLogSerializer


class SiteAuditLogListAPIView(generics.ListAPIView):
    """
    GET /api/v1/sites/<site_id>/audit-log

    Read-only history of create/update/delete/publish actions for a
    single site. Never written to directly — rows are only ever
    created by AuditService from the service layer.
    """

    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_site(self):
        return get_object_or_404(
            Site,
            pk=self.kwargs["site_id"],
            owner=self.request.user,
        )

    def get_queryset(self):
        site = self.get_site()
        content_type = ContentType.objects.get_for_model(Site)
        return AuditLog.objects.filter(
            content_type=content_type,
            object_id=site.pk,
        ).select_related("actor")
