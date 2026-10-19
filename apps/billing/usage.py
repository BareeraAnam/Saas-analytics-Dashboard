from django.db.models import F
from django.utils import timezone

from .models import UsageRecord


def record_usage(count: int = 1):
    today = timezone.now().date()
    UsageRecord.objects.get_or_create(date=today)
    UsageRecord.objects.filter(date=today).update(calls=F("calls") + count)
