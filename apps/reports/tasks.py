import logging

from celery import shared_task
from django.core.mail import EmailMessage
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from apps.accounts.permissions import unknown_tenant_emails

from .generators import make_csv, make_pdf
from .models import ReportSchedule

logger = logging.getLogger(__name__)


@shared_task
def send_reports(frequency: str):
    for tenant in get_tenant_model().objects.exclude(schema_name="public"):
        try:
            with schema_context(tenant.schema_name):
                for sched in ReportSchedule.objects.filter(is_active=True, frequency=frequency):
                    try:
                        _send(tenant, sched)
                    except Exception:
                        logger.exception("report %s failed for tenant %s", sched.pk, tenant.schema_name)
        except Exception:
            logger.exception("reports failed for tenant %s", tenant.schema_name)


def _send(tenant, sched):
    recipients = sched.recipient_list()
    # Re-check at send time. A user may have been removed after the schedule was saved.
    blocked = unknown_tenant_emails(recipients)
    if blocked:
        raise ValueError(f"recipients are not tenant users: {', '.join(blocked)}")
    if not recipients:
        return
    if sched.file_format == "pdf":
        content, fname, mime = make_pdf(sched.frequency, sched.name), f"{sched.name}.pdf", "application/pdf"
    else:
        content, fname, mime = make_csv(sched.frequency), f"{sched.name}.csv", "text/csv"
    mail = EmailMessage(f"[{tenant.name}] {sched.name}", "Report attached.", None, recipients)
    mail.attach(fname, content, mime)
    mail.send()
    sched.last_sent_at = timezone.now()
    sched.save(update_fields=["last_sent_at"])
