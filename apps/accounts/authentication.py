from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework import authentication, exceptions

from .models import APIKey, hash_key


class APIKeyAuthentication(authentication.BaseAuthentication):
    """Header: Authorization: Api-Key sk_xxx"""

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Api-Key "):
            return None
        raw = header.split(" ", 1)[1].strip()
        try:
            key = APIKey.objects.get(key_hash=hash_key(raw), is_active=True)
        except APIKey.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid API key")
        APIKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        # AnonymousUser has is_authenticated. Returning None as the user makes
        # later code crash when it touches request.user.is_authenticated.
        return (AnonymousUser(), key)

    def authenticate_header(self, request):
        return "Api-Key"
