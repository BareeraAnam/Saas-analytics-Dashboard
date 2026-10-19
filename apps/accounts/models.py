import hashlib
import secrets

from django.conf import settings
from django.db import models


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class APIKey(models.Model):
    """API key for one tenant. The raw key and the signing secret are shown once."""

    name = models.CharField(max_length=60)
    # Public id sent as X-Key-Id. This is not a secret; it only picks the row.
    key_id = models.CharField(max_length=24, unique=True)
    prefix = models.CharField(max_length=12, db_index=True)
    key_hash = models.CharField(max_length=64, unique=True)
    # Stored so we can check the HMAC. The client never sends this value.
    # Hashing it would make verification impossible, because HMAC needs the raw secret.
    signing_secret = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def create_key(cls, name):
        raw = "sk_" + secrets.token_urlsafe(32)
        signing_secret = secrets.token_urlsafe(32)
        obj = cls.objects.create(
            name=name,
            key_id="ak_" + secrets.token_hex(8),
            prefix=raw[:10],
            key_hash=hash_key(raw),
            signing_secret=signing_secret,
        )
        return obj, raw, signing_secret


class Membership(models.Model):
    """Role inside this tenant. The first user is the owner; invited users are not."""

    OWNER = "owner"
    MEMBER = "member"
    VIEWER = "viewer"
    ROLES = [(OWNER, "Owner"), (MEMBER, "Member"), (VIEWER, "Viewer")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership")
    role = models.CharField(max_length=10, choices=ROLES, default=MEMBER)
