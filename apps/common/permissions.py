from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """
    Generic object-level permission.

    Assumes the model has an `owner` field.
    """

    def has_object_permission(self, request, view, obj):
        return obj.owner == request.user