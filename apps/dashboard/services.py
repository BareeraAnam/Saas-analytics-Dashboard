import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.db import connection
from django.db.models import Count, Sum
from django.db.models.functions import TruncHour
from django.utils import timezone

from apps.ingestion.models import Event

logger = logging.getLogger(__name__)

CACHE_KEY = "dashboard:summary"
CACHE_TTL = 30
# One live push per tenant in this window. A burst of ingests would otherwise
# expire the cache on every request and make every socket recompute it.
PUSH_EVERY_SECONDS = 5


def build_summary(hours: int = 24) -> dict:
    since = timezone.now() - timedelta(hours=hours)
    qs = Event.objects.filter(timestamp__gte=since)
    by_name = list(qs.values("name").annotate(total=Sum("value"), n=Count("id")).order_by("-total")[:10])
    series = list(qs.annotate(h=TruncHour("timestamp")).values("h", "name")
                  .annotate(total=Sum("value")).order_by("h"))
    return {
        "total_events": qs.count(),
        "by_name": by_name,
        "series": [{"hour": r["h"].isoformat(), "name": r["name"], "total": r["total"]} for r in series],
    }


def get_summary() -> dict:
    data = cache.get(CACHE_KEY)
    if data is None:
        data = build_summary()
        cache.set(CACHE_KEY, data, CACHE_TTL)
    return data


def publish_summary():
    """Compute the summary once and send that payload to the group."""
    cache.delete(CACHE_KEY)
    data = get_summary()
    try:
        async_to_sync(get_channel_layer().group_send)(
            f"metrics_{connection.schema_name}",
            {"type": "metrics.update", "summary": data},
        )
    except Exception:
        logger.exception("metrics push failed")
    return data


def schedule_metrics_push():
    schema = connection.schema_name
    if cache.add("metrics:debounce", "1", PUSH_EVERY_SECONDS):
        publish_summary()
        return
    # The first push in the window already happened. One follow-up covers
    # the events that arrived after it, instead of pushing on every request.
    if cache.add("metrics:debounce-tail", "1", PUSH_EVERY_SECONDS):
        from apps.dashboard.tasks import broadcast_tenant_summary
        broadcast_tenant_summary.apply_async(args=[schema], countdown=PUSH_EVERY_SECONDS)
