from rest_framework import filters, generics, permissions, status
from rest_framework.response import Response
from apps.common.permissions import CanDelete, HasUpdate, IsOwner
from apps.common.services import LockService

from .models import Page
from .serializers import PageSerializer
from .services import PageService


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
            .filter(site__owner=self.request.user)
        )

    def update(self, request, *args, **kwargs):
        # Check lock before allowing update
        page = self.get_object()
        lock_status = LockService.get_lock_status('page', page.id)
        if lock_status['locked']:
            locker = lock_status['locker']
            message = f"This page is currently being edited by {locker.username if locker else 'someone'}."
            return Response(
                {"detail": message},
                status=status.HTTP_409_CONFLICT
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        # Check lock before allowing delete
        page = self.get_object()
        lock_status = LockService.get_lock_status('page', page.id)
        if lock_status['locked']:
            locker = lock_status['locker']
            message = f"This page is currently being edited by {locker.username if locker else 'someone'}."
            return Response(
                {"detail": message},
                status=status.HTTP_409_CONFLICT
            )
        return super().destroy(request, *args, **kwargs)

    def perform_update(self, serializer):
        PageService.update_page(
            serializer.instance,
            **serializer.validated_data,
        )


class PageLockAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = Page.objects.all()

    def get_queryset(self):
        return (
            Page.objects
            .select_related("site")
            .filter(site__owner=self.request.user)
        )

    def post(self, request, pk):
        page = self.get_object()
        lock_result = LockService.acquire_lock('page', page.id, request.user.id)
        
        if lock_result['success']:
            return Response({"detail": "Lock acquired successfully!"})
        else:
            locker = lock_result['locker']
            message = f"This page is currently being edited by {locker.username if locker else 'someone'}."
            return Response(
                {"detail": message},
                status=status.HTTP_409_CONFLICT
            )

    def delete(self, request, pk):
        page = self.get_object()
        released = LockService.release_lock('page', page.id, request.user.id)
        
        if released:
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                {"detail": "You cannot release this lock."},
                status=status.HTTP_403_FORBIDDEN
            )

class PageHeartbeatAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = Page.objects.all()

    def get_queryset(self):
        return (
            Page.objects
            .select_related("site")
            .filter(site__owner=self.request.user)
        )
    
    def post(self, request, pk):
        page = self.get_object()
        alive = LockService.heartbeat(
            "page",
            page.id,
            request.user.id,
        )  
        if alive:
            return Response({
                "detail": "Heartbeat received."
            })
        
        return Response(
            {
                "detail": "Lock not found or you are not the owner."
            },
            status=status.HTTP_403_FORBIDDEN
        )