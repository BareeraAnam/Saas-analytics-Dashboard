import logging

from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.authentication import APIKeyAuthentication
from apps.accounts.models import APIKey
from apps.accounts.permissions import HasAPIKey
from apps.billing.usage import record_usage
from apps.dashboard.services import schedule_metrics_push

from .models import Event
from .serializers import EventSerializer
from .signatures import verified_key

logger = logging.getLogger(__name__)

# The throttle counts requests. This caps how many events one request can add.
MAX_BATCH = 1000
MAX_BODY_BYTES = 1_048_576


def check_batch(data):
    if isinstance(data, list) and len(data) > MAX_BATCH:
        raise ValidationError(f"Too many events in one request (max {MAX_BATCH}).")


def check_body_size(request):
    if len(request.body) > MAX_BODY_BYTES:
        raise ValidationError("Request body is too large.")


def after_ingest(count: int):
    """Count the call for billing, then push one shared dashboard update."""
    record_usage(count)
    try:
        schedule_metrics_push()
    except Exception:
        # A cache or Redis problem must not fail the ingest that already saved.
        logger.exception("live metrics update failed")


class IngestView(APIView):
    """POST /api/ingest/ accepts one event or a list of events."""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ingest"

    def post(self, request):
        check_body_size(request)
        check_batch(request.data)
        many = isinstance(request.data, list)
        incoming = EventSerializer(data=request.data, many=many)
        incoming.is_valid(raise_exception=True)
        items = incoming.validated_data if many else [incoming.validated_data]
        Event.objects.bulk_create([Event(source="api", **item) for item in items])
        after_ingest(len(items))
        return Response({"received": len(items)}, status=201)


class WebhookView(APIView):
    """POST /api/webhook/

    Headers: X-Key-Id, X-Signature: t=<unix>,v1=<hex hmac of "{t}.{body}">.
    The HMAC uses the signing secret, which is not in the request.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "webhook"

    def post(self, request):
        # Returned directly. Raising AuthenticationFailed becomes 403 here,
        # because this view has no authenticator to set a WWW-Authenticate header.
        key = verified_key(
            request.headers.get("X-Key-Id", ""),
            request.headers.get("X-Signature", ""),
            request.body,
        )
        if key is None:
            return Response({"detail": "bad signature"}, status=401)
        APIKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        check_body_size(request)
        check_batch(request.data)
        payload = request.data if isinstance(request.data, list) else [request.data]
        incoming = EventSerializer(data=payload, many=True)
        incoming.is_valid(raise_exception=True)
        Event.objects.bulk_create([
            Event(source="webhook", **item) for item in incoming.validated_data
        ])
        after_ingest(len(payload))
        return Response({"received": len(payload)}, status=201)
