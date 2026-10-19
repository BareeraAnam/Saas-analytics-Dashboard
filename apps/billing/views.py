import stripe
from django.conf import settings
from django.db import connection
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsOwner, IsTenantMember
from apps.tenants.models import Client

from .models import UsageRecord


class UsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageRecord
        fields = ["date", "calls", "reported_calls"]


class UsageView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response(UsageSerializer(UsageRecord.objects.order_by("-date")[:31], many=True).data)


class SubscribeView(APIView):
    permission_classes = [IsOwner]

    def post(self, request):
        if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_METERED_PRICE_ID:
            return Response({"detail": "Billing is not configured."}, status=503)
        stripe.api_key = settings.STRIPE_SECRET_KEY
        tenant = Client.objects.get(schema_name=connection.schema_name)
        if tenant.subscription_status == "active":
            return Response({"detail": "Already subscribed."}, status=400)
        if not tenant.stripe_customer_id:
            customer = stripe.Customer.create(name=tenant.name, email=request.user.email)
            tenant.stripe_customer_id = customer.id
            # Status stays empty until the webhook confirms checkout.
            tenant.save(update_fields=["stripe_customer_id"])
        primary = tenant.get_primary_domain()
        if primary is None:
            return Response({"detail": "Tenant has no domain."}, status=400)
        # Built from the stored domain. request.build_absolute_uri would follow
        # the Host header, which used to be allowed to be anything.
        scheme = "https" if not settings.DEBUG else "http"
        port = "" if not settings.DEBUG else ":8000"
        base = f"{scheme}://{primary.domain}{port}/"
        session = stripe.checkout.Session.create(
            customer=tenant.stripe_customer_id,
            mode="subscription",
            line_items=[{"price": settings.STRIPE_METERED_PRICE_ID}],
            success_url=base + "?billing=ok",
            cancel_url=base + "?billing=cancel",
        )
        return Response({"checkout_url": session.url})


class StripeWebhookView(APIView):
    """Stripe calls this on the public host. The signature is the authentication."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.STRIPE_WEBHOOK_SECRET:
            return Response({"detail": "Webhook is not configured."}, status=503)
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            event = stripe.Webhook.construct_event(
                request.body,
                request.headers.get("Stripe-Signature", ""),
                settings.STRIPE_WEBHOOK_SECRET,
            )
        except (ValueError, stripe.SignatureVerificationError):
            return Response({"detail": "bad signature"}, status=400)
        _apply_event(event)
        return Response({"received": True})


def _apply_event(event):
    obj = event["data"]["object"]
    customer_id = obj.get("customer")
    if not customer_id:
        return
    tenant = Client.objects.filter(stripe_customer_id=customer_id).first()
    if tenant is None:
        return
    kind = event["type"]
    if kind == "checkout.session.completed":
        tenant.subscription_status = "active"
    elif kind in ("customer.subscription.updated", "customer.subscription.deleted"):
        tenant.subscription_status = obj.get("status") or "canceled"
    else:
        return
    tenant.save(update_fields=["subscription_status"])
