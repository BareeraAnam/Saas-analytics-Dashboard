from django.db import models


class Event(models.Model):
    # No standalone index on name. The (name, timestamp) index already covers
    # lookups that start with the name, which is what alerts do.
    name = models.CharField(max_length=100)
    value = models.FloatField(default=1)
    properties = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=30, default="api")
    timestamp = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=["name", "timestamp"])]
