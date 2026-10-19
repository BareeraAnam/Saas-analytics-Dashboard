import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from .models import Event

logger = logging.getLogger(__name__)


@shared_task
def prune_old_events():
    # One tenant's failure must not skip the rest. Raw events are not kept forever;
    # the dashboard only needs a recent window and the table would otherwise grow without a bound.
    cutoff = timezone.now() - timedelta(days=settings.EVENT_RETENTION_DAYS)
    for tenant in get_tenant_model().objects.exclude(schema_name="public"):
        try:
            with schema_context(tenant.schema_name):
                Event.objects.filter(timestamp__lt=cutoff).delete()
        except Exception:
            logger.exception("event prune failed for tenant %s", tenant.schema_name)
