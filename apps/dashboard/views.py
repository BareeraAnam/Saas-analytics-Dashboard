from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantMember

from .services import get_summary


class SummaryView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response(get_summary())


@login_required(login_url="/login/")
def dashboard_page(request):
    return render(request, "dashboard/index.html")
