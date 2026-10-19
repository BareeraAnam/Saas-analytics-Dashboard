from django.db import models


class AlertRule(models.Model):
    OPS = [("gt", ">"), ("lt", "<"), ("gte", ">="), ("lte", "<=")]
    name = models.CharField(max_length=100)
    metric = models.CharField(max_length=100)
    operator = models.CharField(max_length=3, choices=OPS, default="gt")
    threshold = models.FloatField()
    window_minutes = models.PositiveIntegerField(default=5)
    notify_email = models.EmailField(blank=True)
    webhook_url = models.URLField(blank=True)
    cooldown_minutes = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class AlertLog(models.Model):
    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name="logs")
    value = models.FloatField()
    triggered_at = models.DateTimeField(auto_now_add=True)
