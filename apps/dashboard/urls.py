from django.urls import path
from .views import SummaryView

urlpatterns = [path("dashboard/summary/", SummaryView.as_view())]
