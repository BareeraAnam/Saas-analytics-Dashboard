import hashlib
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import serializers

from .models import Client, Domain, PendingSignup

# Hostnames cannot contain underscores. SlugField allows them, and signup used
# to turn both "foo-bar" and "foo_bar" into the schema name foo_bar.
SUBDOMAIN_RE = re.compile(r"^[a-z][a-z0-9-]{2,30}$")
RESERVED = {"www", "admin", "api", "public", "localhost", "mail", "static"}
SIGNUP_TTL = timedelta(hours=24)
logger = logging.getLogger(__name__)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class SignupSerializer(serializers.Serializer):
    company = serializers.CharField(max_length=100)
    subdomain = serializers.CharField(max_length=50)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)

    def validate_subdomain(self, value):
        value = value.lower()
        if not SUBDOMAIN_RE.match(value):
            raise serializers.ValidationError(
                "3-31 chars, lowercase letters/numbers/hyphen, must start with a letter."
            )
        if value in RESERVED:
            raise serializers.ValidationError("Reserved subdomain.")
        schema = value.replace("-", "_")
        # Postgres reserves schema names that start with pg_.
        if schema.startswith("pg_"):
            raise serializers.ValidationError("Reserved name.")
        if Domain.objects.filter(domain=f"{value}.{settings.BASE_DOMAIN}").exists():
            raise serializers.ValidationError("Subdomain already taken.")
        if Client.objects.filter(schema_name=schema).exists():
            raise serializers.ValidationError("Subdomain already taken.")
        pending = PendingSignup.objects.filter(subdomain=value).exclude(status=PendingSignup.DONE).first()
        if pending and timezone.now() - pending.created_at < SIGNUP_TTL:
            raise serializers.ValidationError("Subdomain already taken.")
        return value

    def create(self, data):
        token = secrets.token_urlsafe(32)
        pending = PendingSignup.objects.create(
            company=data["company"],
            subdomain=data["subdomain"],
            email=data["email"],
            password_hash=make_password(data["password"]),
            token_hash=hash_token(token),
        )
        scheme = "https" if not settings.DEBUG else "http"
        port = "" if not settings.DEBUG else ":8000"
        link = f"{scheme}://{settings.BASE_DOMAIN}{port}/api/signup/verify/{token}/"
        # Printed on purpose in local DEBUG so the link is visible in runserver
        # even when the console email is easy to miss.
        if settings.DEBUG:
            logger.warning("Signup confirmation link: %s", link)
        try:
            send_mail(
                "Confirm your analytics workspace",
                f"Open this link to finish creating {data['subdomain']}: {link}",
                None,
                [data["email"]],
            )
        except Exception:
            pending.delete()
            raise serializers.ValidationError("Could not send the verification email.")
        pending.raw_token = token
        return pending
