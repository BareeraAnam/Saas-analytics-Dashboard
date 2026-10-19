import logging

import stripe
from celery import shared_task
from django.conf import settings
from django.db.models import F
from django_tenants.utils import get_tenant_model, schema_context

from .models import UsageRecord

logger = logging.getLogger(__name__)


@shared_task
def report_usage_to_stripe():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    if not stripe.api_key:
        return
    tenants = (
        get_tenant_model().objects.exclude(schema_name="public")
        .exclude(stripe_customer_id="")
        # The customer id is saved when checkout starts. Billing waits until
        # the webhook marks the subscription active, so a cancelled checkout is not charged.
        .filter(subscription_status="active")
    )
    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                for rec in UsageRecord.objects.filter(calls__gt=F("reported_calls")):
                    delta = rec.calls - rec.reported_calls
                    # Same key on a retry. If we crash after Stripe accepts the event
                    # and before reported_calls is saved, the next run does not bill it again.
                    idempotency_key = f"{tenant.schema_name}-{rec.date.isoformat()}-{rec.calls}"
                    stripe.billing.MeterEvent.create(
                        event_name="api_call",
                        identifier=idempotency_key,
                        payload={"value": str(delta), "stripe_customer_id": tenant.stripe_customer_id},
                        idempotency_key=idempotency_key,
                    )
                    rec.reported_calls = rec.calls
                    rec.save(update_fields=["reported_calls"])
        except Exception:
            logger.exception("usage report failed for tenant %s", tenant.schema_name)
