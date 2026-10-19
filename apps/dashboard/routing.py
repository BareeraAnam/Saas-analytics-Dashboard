from django.urls import path
from .consumers import MetricsConsumer

websocket_urlpatterns = [path("ws/metrics/", MetricsConsumer.as_asgi())]
