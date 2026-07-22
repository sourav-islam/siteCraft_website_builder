from rest_framework import filters, generics, permissions, status
from rest_framework.response import Response
from apps.common.permissions import CanDelete, HasUpdate, IsOwner
from apps.common.services import LockService

from .models import Site
from .serializers import SiteSerializer
from .services import SiteService


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
            locker = lock_status['locker']
            message = f"This site is currently being edited by {locker.username if locker else 'someone'}."
            return Response(
                {"detail": message},
                status=status.HTTP_409_CONFLICT
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        # Check lock before allowing delete
        site = self.get_object()
        lock_status = LockService.get_lock_status('site', site.id)
        if lock_status['locked']:
            locker = lock_status['locker']
            message = f"This site is currently being edited by {locker.username if locker else 'someone'}."
            return Response(
                {"detail": message},
                status=status.HTTP_409_CONFLICT
            )
        return super().destroy(request, *args, **kwargs)


class SiteLockAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    queryset = Site.objects.all()

    def post(self, request, pk):
        site = self.get_object()
        lock_result = LockService.acquire_lock('site', site.id, request.user.id)
        
        if lock_result['success']:
            return Response({"detail": "Lock acquired successfully!"})
        else:
            locker = lock_result['locker']
            message = f"This site is currently being edited by {locker.username if locker else 'someone'}."
            return Response(
                {"detail": message},
                status=status.HTTP_409_CONFLICT
            )

    def delete(self, request, pk):
        site = self.get_object()
        released = LockService.release_lock('site', site.id, request.user.id)
        
        if released:
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                {"detail": "You cannot release this lock."},
                status=status.HTTP_403_FORBIDDEN
            )
