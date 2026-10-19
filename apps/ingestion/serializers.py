import json
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import Event

# One event's properties must stay small. The batch cap alone does not stop
# a single huge JSON blob.
MAX_PROPERTIES_BYTES = 8_000
# Clients must not backfill an arbitrary history or stamp events in the future.
MAX_PAST = timedelta(days=7)
MAX_FUTURE = timedelta(minutes=5)


class EventSerializer(serializers.ModelSerializer):
    timestamp = serializers.DateTimeField(required=False)

    class Meta:
        model = Event
        fields = ["name", "value", "properties", "timestamp"]

    def validate_properties(self, value):
        if len(json.dumps(value).encode()) > MAX_PROPERTIES_BYTES:
            raise serializers.ValidationError("properties is too large")
        return value

    def validate_timestamp(self, value):
        now = timezone.now()
        if value < now - MAX_PAST or value > now + MAX_FUTURE:
            raise serializers.ValidationError("timestamp is outside the allowed window")
        return value

    def validate(self, attrs):
        attrs.setdefault("timestamp", timezone.now())
        return attrs
