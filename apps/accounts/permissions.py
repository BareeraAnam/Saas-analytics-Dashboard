from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.functions import Lower
from rest_framework.permissions import BasePermission

from .models import APIKey, Membership


class HasAPIKey(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.auth, APIKey)


def _role(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.membership.role
    except ObjectDoesNotExist:
        return None


class IsTenantMember(BasePermission):
    """Any role may read. Viewers cannot change data."""

    def has_permission(self, request, view):
        role = _role(request.user)
        if role is None:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return role in (Membership.OWNER, Membership.MEMBER)


class IsOwner(BasePermission):
    def has_permission(self, request, view):
        return _role(request.user) == Membership.OWNER


def unknown_tenant_emails(emails):
    """Addresses that are not an active user of the current tenant.

    Alert and report mail used to accept any address, which turned the app
    into an open mail relay.
    """
    if not emails:
        return []
    existing = set(
        get_user_model().objects.filter(is_active=True)
        .annotate(lower_email=Lower("email"))
        .values_list("lower_email", flat=True)
    )
    return [email for email in emails if email.lower() not in existing]
