from django.contrib import admin
from django.urls import include, path

from apps.billing.views import StripeWebhookView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.tenants.urls")),
    # One Stripe endpoint for every tenant. It lives on the public host.
    path("api/billing/webhook/", StripeWebhookView.as_view()),
]
