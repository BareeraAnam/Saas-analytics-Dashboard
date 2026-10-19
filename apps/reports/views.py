from django.http import HttpResponse
from rest_framework import serializers, viewsets
from rest_framework.decorators import action

from apps.accounts.permissions import IsTenantMember, unknown_tenant_emails

from .generators import make_csv, make_pdf
from .models import ReportSchedule


class ReportScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportSchedule
        fields = "__all__"
        read_only_fields = ["last_sent_at"]

    def validate_recipients(self, value):
        emails = [part.strip() for part in value.split(",") if part.strip()]
        if not emails:
            raise serializers.ValidationError("At least one recipient is required.")
        missing = unknown_tenant_emails(emails)
        if missing:
            raise serializers.ValidationError(
                "Recipients must be users of this tenant: " + ", ".join(missing)
            )
        return ", ".join(emails)


class ReportScheduleViewSet(viewsets.ModelViewSet):
    queryset = ReportSchedule.objects.all()
    serializer_class = ReportScheduleSerializer
    permission_classes = [IsTenantMember]

    @action(detail=False, methods=["get"], url_path="download")
    def download(self, request):
        fmt = request.query_params.get("fmt", "csv")
        freq = request.query_params.get("frequency", "daily")
        if fmt == "pdf":
            return HttpResponse(make_pdf(freq), content_type="application/pdf")
        return HttpResponse(make_csv(freq), content_type="text/csv")
