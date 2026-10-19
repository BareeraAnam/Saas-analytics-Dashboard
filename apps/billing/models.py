from django.db import models


class UsageRecord(models.Model):
    date = models.DateField(unique=True)
    calls = models.PositiveBigIntegerField(default=0)
    reported_calls = models.PositiveBigIntegerField(default=0)
