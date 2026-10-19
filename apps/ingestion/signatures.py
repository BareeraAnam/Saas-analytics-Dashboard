import hashlib
import hmac
import logging
import time

from django.core.cache import cache

from apps.accounts.models import APIKey

logger = logging.getLogger(__name__)

# Captured requests older than this are rejected. A seen signature is also
# stored for this long, so the same body cannot be accepted twice inside the window.
MAX_SKEW_SECONDS = 300


def sign_body(secret: str, body: bytes, timestamp: int) -> str:
    payload = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verified_key(key_id: str, signature_header: str, body: bytes):
    """Look the key up by its public id and check a signature made with the
    signing secret. The raw API key is not the HMAC key: anyone holding the
    key could otherwise forge the signature, so the HMAC would prove nothing.
    """
    parts = {}
    for item in (signature_header or "").split(","):
        if "=" in item:
            name, value = item.split("=", 1)
            parts[name.strip()] = value.strip()
    timestamp = parts.get("t")
    given = parts.get("v1", "")
    try:
        key = APIKey.objects.get(key_id=key_id, is_active=True)
        secret = key.signing_secret
    except APIKey.DoesNotExist:
        key = None
        # Still do a compare so a missing id is not faster than a bad signature.
        secret = "0" * 32
    try:
        stamp = int(timestamp)
    except (TypeError, ValueError):
        stamp = 0
    expected = sign_body(secret, body, stamp)
    if len(given) != len(expected):
        given = "0" * len(expected)
    fresh = abs(int(time.time()) - stamp) <= MAX_SKEW_SECONDS
    if key is None or not fresh or not hmac.compare_digest(expected, given):
        return None
    # cache.add is atomic. The second copy of this exact signature loses.
    # If Redis is down we reject, because accepting would allow a replay.
    seen = f"webhook-seen:{key.key_id}:{stamp}:{given}"
    try:
        first_time = cache.add(seen, 1, timeout=MAX_SKEW_SECONDS)
    except Exception:
        logger.exception("webhook replay cache failed")
        return None
    if not first_time:
        return None
    return key
