from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """
    Generic object-level permission.

    Assumes the model has an `owner` field.
    """

    def has_object_permission(self, request, view, obj):
        return obj.site.owner == request.user


class HasUpdate(BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if hasattr(obj, "site"):
            return obj.site.owner == request.user

        return obj.owner == request.user


class CanDelete(BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if hasattr(obj, "site"):
            return obj.site.owner == request.user

        return obj.owner == request.user