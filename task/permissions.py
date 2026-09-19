from rest_framework.permissions import BasePermission
from accounts.models import User

class IsStoreManager(BasePermission):
    message = "Only store manager can access this endpoint"
    def has_permission(self, request, view):
        return (
                request.user.is_authenticated
                and request.user.role == User.Role.STORE_MANAGER
        )

class IsDeliveryPerson(BasePermission):
    message = "Only delivery person can access this endpoint"
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.Role.DELIVERY_PERSON
        )