from django.urls import path

from .views import SiteAuditLogListAPIView

urlpatterns = [
    path("", SiteAuditLogListAPIView.as_view(), name="site-audit-log"),
]