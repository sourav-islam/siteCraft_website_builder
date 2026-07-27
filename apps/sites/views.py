from rest_framework import filters, generics, permissions, status
from rest_framework.response import Response
from apps.common.permissions import CanDelete, HasUpdate, IsOwner
from apps.common.services import LockService

from .models import Site
from .serializers import SiteSerializer
from .services import SiteService


def _site_info(site):
    """Build a lightweight site info dict for lock/heartbeat responses."""
    return {
        "id": site.id,
        "name": site.name,
        "description": site.description,
        "owner_id": site.owner_id,
        "status": site.status,
        "is_public": site.is_public,
    }


class SiteListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = SiteSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsOwner,
    ]
    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = [
        "name",
        "description"
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


class SiteRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SiteSerializer
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
        return Site.objects.filter(
            owner=self.request.user
        )

    def update(self, request, *args, **kwargs):
        # Check lock before allowing update
        site = self.get_object()
        lock_status = LockService.get_lock_status('site', site.id)
        if lock_status['locked']:
            locker = lock_status.get('locker')
            locker_name = locker['username'] if locker else 'someone'
            return Response(
                {
                    "detail": f"This site is currently being edited by {locker_name}.",
                    "code": "site_locked",
                    "site": _site_info(site),
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
        # Check lock before allowing delete
        site = self.get_object()
        lock_status = LockService.get_lock_status('site', site.id)
        if lock_status['locked']:
            locker = lock_status.get('locker')
            locker_name = locker['username'] if locker else 'someone'
            return Response(
                {
                    "detail": f"This site is currently being edited by {locker_name}.",
                    "code": "site_locked",
                    "site": _site_info(site),
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


class SiteLockAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    queryset = Site.objects.all()

    def get(self, request, pk):
        """GET lock status for a site — public read check."""
        site = self.get_object()
        lock_status = LockService.get_lock_status('site', site.id)

        response_data = {
            "detail": "Site is available for editing." if not lock_status["locked"] else "Site is currently locked.",
            "site": _site_info(site),
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

    def post(self, request, pk):
        """POST — acquire a lock for a site."""
        site = self.get_object()
        lock_result = LockService.acquire_lock('site', site.id, request.user.id)

        base_response = {
            "site": _site_info(site),
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
            base_response["detail"] = f"This site is currently being edited by {locker_name}."
            base_response["code"] = "site_locked"
            return Response(base_response, status=status.HTTP_409_CONFLICT)

    def delete(self, request, pk):
        """DELETE — release a lock for a site. Returns JSON body (not empty 204)."""
        site = self.get_object()
        release_result = LockService.release_lock('site', site.id, request.user.id)

        base_response = {
            "site": _site_info(site),
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


class SiteHeartbeatAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    queryset = Site.objects.all()
    
    def post(self, request, pk):
        """POST — refresh lock TTL via heartbeat for a site."""
        site = self.get_object()
        hb_result = LockService.heartbeat(
            "site",
            site.id,
            request.user.id,
        )

        base_response = {
            "site": _site_info(site),
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


class SitePublishAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, HasUpdate]
    queryset = Site.objects.all()
    serializer_class = SiteSerializer

    def get_queryset(self):
        return Site.objects.filter(owner=self.request.user)

    def post(self, request, pk):
        site = self.get_object()

        lock_status = LockService.get_lock_status("site", site.id)
        if lock_status["locked"]:
            locker = lock_status.get("locker") or {}
            if locker and locker.get("id") != request.user.id:
                locker_name = locker.get("username") or "someone"
                return Response(
                    {
                        "detail": f"Site is locked by {locker_name}; ask them to release or wait for lock expiry.",
                        "code": "site_locked",
                        "site": _site_info(site),
                        "lock": {
                            "locked": True,
                            "locker": locker,
                            "ttl_remaining": lock_status.get("ttl_remaining"),
                            "lock_key": lock_status.get("lock_key"),
                        },
                    },
                    status=status.HTTP_423_LOCKED,
                )

        from django.core.exceptions import ValidationError as DjValidationError
        from apps.sites.services import PublishService

        try:
            svc = PublishService(request=request)
            result = svc.publish(site)
        except DjValidationError as exc:
            errors = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
            return Response(
                {"detail": "Publish validation failed.", "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "detail": "Publish failed unexpectedly.",
                    "errors": {"detail": [str(exc)]},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result, status=status.HTTP_200_OK)