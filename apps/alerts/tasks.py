import json
import logging
import operator as op
import urllib.request
from datetime import timedelta

from celery import shared_task
from django.core.mail import send_mail
from django.db.models import Sum
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from apps.accounts.permissions import unknown_tenant_emails
from apps.ingestion.models import Event

from .models import AlertLog, AlertRule
from .safety import is_safe_webhook_url

logger = logging.getLogger(__name__)

OPS = {"gt": op.gt, "lt": op.lt, "gte": op.ge, "lte": op.le}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # A redirect could point at a private address after the first check passed.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@shared_task
def check_all_alerts():
    for tenant in get_tenant_model().objects.exclude(schema_name="public"):
        # One tenant's SMTP or webhook error must not skip every tenant after it.
        try:
            with schema_context(tenant.schema_name):
                for rule in AlertRule.objects.filter(is_active=True):
                    try:
                        _check_rule(tenant, rule)
                    except Exception:
                        logger.exception("alert rule %s failed for tenant %s", rule.pk, tenant.schema_name)
        except Exception:
            logger.exception("alert check failed for tenant %s", tenant.schema_name)


def _check_rule(tenant, rule):
    now = timezone.now()
    if rule.last_triggered_at and now - rule.last_triggered_at < timedelta(minutes=rule.cooldown_minutes):
        return
    since = now - timedelta(minutes=rule.window_minutes)
    value = Event.objects.filter(name=rule.metric, timestamp__gte=since).aggregate(s=Sum("value"))["s"] or 0
    if not OPS[rule.operator](value, rule.threshold):
        return
    rule.last_triggered_at = now
    rule.save(update_fields=["last_triggered_at"])
    AlertLog.objects.create(rule=rule, value=value)
    msg = (
        f"[{tenant.name}] Alert '{rule.name}': {rule.metric} = {value} "
        f"(rule {rule.operator} {rule.threshold} in {rule.window_minutes}m)"
    )
    if rule.notify_email and not unknown_tenant_emails([rule.notify_email]):
        send_mail(f"Alert: {rule.name}", msg, None, [rule.notify_email])
    elif rule.notify_email:
        logger.warning("skipped alert email to a non-user for tenant %s", tenant.schema_name)
    if rule.webhook_url:
        _post_webhook(rule.webhook_url, msg)


def _post_webhook(url, msg):
    if not is_safe_webhook_url(url):
        logger.warning("blocked alert webhook to a non-public address")
        return
    req = urllib.request.Request(
        url,
        data=json.dumps({"text": msg}).encode(),
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(req, timeout=5).close()
    except Exception:
        logger.exception("alert webhook request failed")
