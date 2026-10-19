from django.db import models


class ReportSchedule(models.Model):
    FREQ = [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")]
    FORMAT = [("csv", "CSV"), ("pdf", "PDF")]
    name = models.CharField(max_length=100)
    frequency = models.CharField(max_length=10, choices=FREQ, default="daily")
    file_format = models.CharField(max_length=3, choices=FORMAT, default="csv")
    recipients = models.TextField(help_text="Comma separated emails")
    is_active = models.BooleanField(default=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    def recipient_list(self):
        return [e.strip() for e in self.recipients.split(",") if e.strip()]
