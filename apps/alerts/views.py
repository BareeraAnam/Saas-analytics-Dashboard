from rest_framework import serializers, viewsets

from apps.accounts.permissions import IsTenantMember, unknown_tenant_emails

from .models import AlertLog, AlertRule
from .safety import is_safe_webhook_url


class AlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertRule
        fields = "__all__"
        read_only_fields = ["last_triggered_at"]

    def validate_notify_email(self, value):
        if value and unknown_tenant_emails([value]):
            raise serializers.ValidationError("Alerts can only be sent to a user of this tenant.")
        return value

    def validate_webhook_url(self, value):
        if value and not is_safe_webhook_url(value):
            raise serializers.ValidationError("Webhook URL must be a public http(s) address.")
        return value


class AlertLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertLog
        fields = "__all__"


class AlertRuleViewSet(viewsets.ModelViewSet):
    queryset = AlertRule.objects.all()
    serializer_class = AlertRuleSerializer
    permission_classes = [IsTenantMember]


class AlertLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AlertLog.objects.all().order_by("-triggered_at")
    serializer_class = AlertLogSerializer
    permission_classes = [IsTenantMember]
