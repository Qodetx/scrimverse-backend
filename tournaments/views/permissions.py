from rest_framework import permissions


class IsHostUser(permissions.BasePermission):
    """Permission class for Host users"""

    def has_permission(self, request, view) -> bool:
        return request.user.is_authenticated and request.user.user_type == "host"


class IsPlayerUser(permissions.BasePermission):
    """Permission class for Player users"""

    def has_permission(self, request, view) -> bool:
        return request.user.is_authenticated and request.user.user_type == "player"
