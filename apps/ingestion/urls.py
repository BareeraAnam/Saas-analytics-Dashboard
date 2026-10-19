from django.urls import path
from .views import IngestView, WebhookView

urlpatterns = [
    path("ingest/", IngestView.as_view()),
    path("webhook/", WebhookView.as_view()),
]
