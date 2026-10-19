from django.urls import path
from .views import SubscribeView, UsageView

urlpatterns = [
    path("billing/usage/", UsageView.as_view()),
    path("billing/subscribe/", SubscribeView.as_view()),
]
