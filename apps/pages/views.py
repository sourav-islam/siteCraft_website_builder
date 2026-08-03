from django.shortcuts import get_object_or_404
from rest_framework import filters, generics, permissions, status
from rest_framework.response import Response
from apps.common.permissions import CanDelete, HasUpdate, IsOwner
from apps.common.services import LockService
from apps.sites.models import Site

from .models import Page
from .serializers import PageSerializer
from .services import PageService


def _page_info(page):
    """Build a lightweight page info dict for lock/heartbeat responses."""
    return {
        "id": page.id,
        "title": page.title,
        "slug": page.slug,
        "site_id": page.site_id,
        "site_name": page.site.name if page.site else None,
        "is_homepage": page.is_homepage,
        "is_published": page.is_published,
    }


class PageListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = PageSerializer
    permission_classes = [
        permissions.IsAuthenticated,
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

    def get_site(self):
        """Resolve site from the URL, 404 if it doesn't exist or isn't owned by the user."""
        return get_object_or_404(
            Site,
            pk=self.kwargs["site_id"],
            owner=self.request.user,
        )

    def get_queryset(self):
        return (
            Page.objects
            .select_related("site")
            .filter(
                site_id=self.kwargs["site_id"],
                site__owner=self.request.user,
            )
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["site"] = self.get_site()
        return context

    def perform_create(self, serializer):
        site = self.get_site()
        PageService.create_page(
            site=site,
            created_by=self.request.user,
            updated_by=self.request.user,
            **serializer.validated_data,
        )


class PageRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PageSerializer
    permission_classes = [
        permissions.IsAuthenticated,
    ]

    def get_permissions(self):
        if self.request.method in ["PUT", "PATCH"]:
            return [permissions.IsAuthenticated(), HasUpdate()]
        if self.request.method == "DELETE":
            return [permissions.IsAuthenticated(), CanDelete()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return (
            Page.objects
            .select_related("site")
            .filter(
                site_id=self.kwargs["site_id"],
                site__owner=self.request.user,
            )
        )

    def update(self, request, *args, **kwargs):
        page = self.get_object()
        lock_status = LockService.get_lock_status('page', page.id)
        if lock_status['locked']:
            locker = lock_status.get('locker')
            locker_name = locker['username'] if locker else 'someone'
            return Response(
                {
                    "detail": f"This page is currently being edited by {locker_name}.",
                    "code": "page_locked",
                    "page": _page_info(page),
                    "lock": {
                        "locked": True,
                        "locker": locker,
                        "ttl_remaining": lock_status.get("ttl_remaining"),
                        "lock_key": lock_status.get("lock_key"),
                    }
                },
                status=status.HTTP_409_CONFLICT
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        page = self.get_object()
        lock_status = LockService.get_lock_status('page', page.id)
        if lock_status['locked']:
            locker = lock_status.get('locker')
            locker_name = locker['username'] if locker else 'someone'
            return Response(
                {
                    "detail": f"This page is currently being edited by {locker_name}.",
                    "code": "page_locked",
                    "page": _page_info(page),
                    "lock": {
                        "locked": True,
                        "locker": locker,
                        "ttl_remaining": lock_status.get("ttl_remaining"),
                        "lock_key": lock_status.get("lock_key"),
                    }
                },
                status=status.HTTP_409_CONFLICT
            )
        return super().destroy(request, *args, **kwargs)

    def perform_update(self, serializer):
        PageService.update_page(
            serializer.instance,
            updated_by=self.request.user,
            **serializer.validated_data,
        )


class PageLockAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = Page.objects.all()

    def get_queryset(self):
        return (
            Page.objects
            .select_related("site")
            .filter(
                site_id=self.kwargs["site_id"],
                site__owner=self.request.user,
            )
        )

    def get(self, request, site_id, pk):
        """GET lock status for a page — public read check."""
        page = self.get_object()
        lock_status = LockService.get_lock_status('page', page.id)

        response_data = {
            "detail": "Page is available for editing." if not lock_status["locked"] else "Page is currently locked.",
            "page": _page_info(page),
            "lock": {
                "locked": lock_status["locked"],
                "lock_key": lock_status.get("lock_key"),
                "resource_type": lock_status.get("resource_type"),
                "resource_id": lock_status.get("resource_id"),
                "locker": lock_status.get("locker"),
                "ttl_seconds": lock_status.get("ttl_seconds"),
                "ttl_remaining": lock_status.get("ttl_remaining"),
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)

    def post(self, request, site_id, pk):
        """POST — acquire a lock for a page."""
        page = self.get_object()
        lock_result = LockService.acquire_lock('page', page.id, request.user.id)

        base_response = {
            "page": _page_info(page),
            "lock": {
                "lock_key": lock_result.get("lock_key"),
                "resource_type": lock_result.get("resource_type"),
                "resource_id": lock_result.get("resource_id"),
                "locked": lock_result.get("locked"),
                "locker": lock_result.get("locker"),
                "ttl_seconds": lock_result.get("ttl_seconds"),
                "ttl_remaining": lock_result.get("ttl_remaining"),
                "acquired_at": lock_result.get("acquired_at"),
            }
        }

        if lock_result['success']:
            base_response["detail"] = "Lock acquired successfully."
            return Response(base_response, status=status.HTTP_200_OK)
        else:
            locker = lock_result.get('locker')
            locker_name = locker['username'] if locker else 'someone'
            base_response["detail"] = f"This page is currently being edited by {locker_name}."
            base_response["code"] = "page_locked"
            return Response(base_response, status=status.HTTP_409_CONFLICT)

    def delete(self, request, site_id, pk):
        """DELETE — release a lock for a page. Returns JSON body (not empty 204)."""
        page = self.get_object()
        release_result = LockService.release_lock('page', page.id, request.user.id)

        base_response = {
            "page": _page_info(page),
            "lock": {
                "lock_key": release_result.get("lock_key"),
                "resource_type": release_result.get("resource_type"),
                "resource_id": release_result.get("resource_id"),
                "locked": release_result.get("locked"),
                "locker": release_result.get("locker"),
                "ttl_remaining": release_result.get("ttl_remaining"),
            },
            "detail": release_result.get("message"),
            "reason": release_result.get("reason"),
        }
        if release_result.get("released_by"):
            base_response["released_by"] = release_result["released_by"]
        if release_result.get("released_at"):
            base_response["released_at"] = release_result["released_at"]

        if release_result['success']:
            return Response(base_response, status=status.HTTP_200_OK)
        else:
            if release_result.get("reason") == "no_lock":
                return Response(base_response, status=status.HTTP_404_NOT_FOUND)
            return Response(base_response, status=status.HTTP_403_FORBIDDEN)


class PageHeartbeatAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = Page.objects.all()

    def get_queryset(self):
        return (
            Page.objects
            .select_related("site")
            .filter(
                site_id=self.kwargs["site_id"],
                site__owner=self.request.user,
            )
        )

    def post(self, request, site_id, pk):
        """POST — refresh lock TTL via heartbeat for a page."""
        page = self.get_object()
        hb_result = LockService.heartbeat(
            "page",
            page.id,
            request.user.id,
        )

        base_response = {
            "page": _page_info(page),
            "lock": {
                "lock_key": hb_result.get("lock_key"),
                "resource_type": hb_result.get("resource_type"),
                "resource_id": hb_result.get("resource_id"),
                "locked": hb_result.get("locked"),
                "locker": hb_result.get("locker"),
                "ttl_seconds": hb_result.get("ttl_seconds"),
                "ttl_remaining": hb_result.get("ttl_remaining"),
                "refreshed_at": hb_result.get("refreshed_at"),
            },
            "detail": hb_result.get("message"),
            "reason": hb_result.get("reason"),
        }

        if hb_result['success']:
            return Response(base_response, status=status.HTTP_200_OK)

        if hb_result.get("reason") == "no_lock":
            return Response(base_response, status=status.HTTP_404_NOT_FOUND)
        return Response(base_response, status=status.HTTP_403_FORBIDDEN)