import json
import time
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.backends.db import SessionStore
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.authentication import APIKeyAuthentication
from apps.accounts.models import APIKey, Membership
from apps.alerts.models import AlertLog, AlertRule
from apps.alerts.safety import is_safe_webhook_url
from apps.alerts.tasks import _check_rule
from apps.billing.models import UsageRecord
from apps.billing.tasks import report_usage_to_stripe
from apps.billing.usage import record_usage
from apps.billing.views import _apply_event
from apps.ingestion.models import Event
from apps.ingestion.signatures import sign_body
from apps.reports.generators import csv_safe, make_csv, report_window
from apps.tenants.models import Client, Domain
from apps.tenants.serializers import SignupSerializer
from config.asgi import application
from config.settings import _flag


class ReviewFixesTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Test Co"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        connection.set_schema_to_public()
        public, _ = Client.objects.get_or_create(
            schema_name=get_public_schema_name(),
            defaults={"name": "Public"},
        )
        Domain.objects.get_or_create(
            domain=settings.BASE_DOMAIN,
            defaults={"tenant": public, "is_primary": True},
        )
        # No schema is created. The row only exists so foo-bar is rejected
        # as a second name for the same schema.
        cls.clash = Client(schema_name="foo_bar", name="Foo")
        cls.clash.auto_create_schema = False
        cls.clash.save()
        cls.other = Client(schema_name="otherco", name="Other")
        cls.other.save()
        cls.other_domain = Domain.objects.create(
            domain="other.test.com", tenant=cls.other, is_primary=True,
        )
        if "other.test.com" not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.append("other.test.com")
        connection.set_tenant(cls.tenant)
        # Committed here, outside the per-test transaction, so the websocket
        # thread (which has its own connection) can see the user and the event.
        from django.utils import timezone as dj_timezone
        Event.objects.create(name="seed", value=1, timestamp=dj_timezone.now())
        User = get_user_model()
        cls.ws_user = User.objects.create_user(
            username="ws@test.com", email="ws@test.com", password="secret1234",
        )
        cls.ws_user.is_staff = True
        cls.ws_user.save()
        Membership.objects.create(user=cls.ws_user, role=Membership.OWNER)
        store = SessionStore()
        store["_auth_user_id"] = str(cls.ws_user.pk)
        store["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        store["_auth_user_hash"] = cls.ws_user.get_session_auth_hash()
        store.save()
        cls.ws_cookie = f"{settings.SESSION_COOKIE_NAME}={store.session_key}".encode()

    @classmethod
    def tearDownClass(cls):
        connection.set_schema_to_public()
        if "other.test.com" in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.remove("other.test.com")
        cls.other_domain.delete()
        cls.other.delete(force_drop=True)
        cls.clash.delete()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        cache.clear()
        connection.set_tenant(self.tenant)
        self.owner = self.make_user("owner@test.com", role=Membership.OWNER)

    def make_user(self, email, password="secret1234", role=Membership.MEMBER):
        connection.set_tenant(self.tenant)
        User = get_user_model()
        user = User.objects.create_user(username=email, email=email, password=password)
        user.is_staff = role == Membership.OWNER
        user.save()
        Membership.objects.create(user=user, role=role)
        return user

    def auth_client(self, user):
        connection.set_tenant(self.tenant)
        client = APIClient(HTTP_HOST=self.domain.domain)
        client.force_login(user)
        return client

    def test_defaults_are_not_wide_open(self):
        self.assertNotIn("*", settings.ALLOWED_HOSTS)
        self.assertTrue(any(host.startswith(".") for host in settings.ALLOWED_HOSTS))
        # Missing USE_REDIS must mean on, so workers share one cache.
        self.assertTrue(_flag("USE_REDIS_IS_UNSET_IN_THIS_TEST", "1"))

    def test_subdomain_rules(self):
        base = {"company": "Acme", "email": "a@acme.com", "password": "secret1234"}
        for bad in ("foo_bar", "ab", "admin", "pg-name", "1abc"):
            incoming = SignupSerializer(data={**base, "subdomain": bad})
            self.assertFalse(incoming.is_valid(), bad)
        # foo-bar and foo_bar would both become schema foo_bar.
        taken = SignupSerializer(data={**base, "subdomain": "foo-bar"})
        self.assertFalse(taken.is_valid())

    def test_api_key_user_is_anonymous_and_ingest_is_isolated(self):
        _obj, raw, _secret = APIKey.create_key("test")
        request = APIRequestFactory().get("/", HTTP_AUTHORIZATION=f"Api-Key {raw}")
        user, _key = APIKeyAuthentication().authenticate(request)
        self.assertFalse(user.is_authenticated)

        client = APIClient(HTTP_HOST=self.domain.domain)
        created = client.post(
            "/api/ingest/",
            {"name": "error", "value": 1},
            format="json",
            HTTP_AUTHORIZATION=f"Api-Key {raw}",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(Event.objects.filter(name="error").count(), 1)

        with schema_context(self.other.schema_name):
            self.assertEqual(Event.objects.count(), 0)
            self.assertFalse(APIKey.objects.filter(key_hash=_obj.key_hash).exists())

    def test_ingest_rejects_oversized_batch_and_old_timestamp(self):
        _obj, raw, _secret = APIKey.create_key("test")
        client = APIClient(HTTP_HOST=self.domain.domain)
        headers = {"HTTP_AUTHORIZATION": f"Api-Key {raw}"}
        too_many = client.post(
            "/api/ingest/",
            [{"name": "n", "value": 1}] * 1001,
            format="json",
            **headers,
        )
        self.assertEqual(too_many.status_code, 400)
        old = client.post(
            "/api/ingest/",
            {"name": "n", "value": 1, "timestamp": "2000-01-01T00:00:00Z"},
            format="json",
            **headers,
        )
        self.assertEqual(old.status_code, 400)
        self.assertFalse(Event.objects.filter(name="n").exists())

    def test_webhook_uses_signing_secret_and_rejects_replay(self):
        obj, raw, secret = APIKey.create_key("hook")
        body = json.dumps({"name": "hook", "value": 2}).encode()
        stamp = int(time.time())
        client = APIClient(HTTP_HOST=self.domain.domain)

        def post(signature):
            return client.post(
                "/api/webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_KEY_ID=obj.key_id,
                HTTP_X_SIGNATURE=signature,
            )

        signature = f"t={stamp},v1={sign_body(secret, body, stamp)}"
        ok = post(signature)
        self.assertEqual(ok.status_code, 201, ok.content)
        # The same signature is still inside the time window, but it was already used.
        again = post(signature)
        self.assertEqual(again.status_code, 401)
        # The raw API key is not the HMAC key. Signing with it must fail.
        forged = post(f"t={stamp},v1={sign_body(raw, body, stamp)}")
        self.assertEqual(forged.status_code, 401)
        old = stamp - 3600
        replay = post(f"t={old},v1={sign_body(secret, body, old)}")
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(Event.objects.filter(source="webhook").count(), 1)

    def test_viewer_cannot_write_and_mail_cannot_leave_the_tenant(self):
        viewer = self.make_user("view@test.com", role=Membership.VIEWER)
        client = self.auth_client(viewer)
        denied = client.post("/api/alerts/rules/", {
            "name": "r", "metric": "error", "operator": "gt", "threshold": 1,
        }, format="json")
        self.assertEqual(denied.status_code, 403)

        owner = self.auth_client(self.owner)
        stranger = owner.post("/api/alerts/rules/", {
            "name": "r", "metric": "error", "operator": "gt", "threshold": 1,
            "notify_email": "stranger@example.com",
        }, format="json")
        self.assertEqual(stranger.status_code, 400)
        metadata = owner.post("/api/alerts/rules/", {
            "name": "r", "metric": "error", "operator": "gt", "threshold": 1,
            "notify_email": self.owner.email,
            "webhook_url": "http://169.254.169.254/latest/meta-data/",
        }, format="json")
        self.assertEqual(metadata.status_code, 400)
        self.assertFalse(is_safe_webhook_url("http://127.0.0.1/hook"))
        self.assertFalse(is_safe_webhook_url("http://localhost/hook"))

        saved = owner.post("/api/alerts/rules/", {
            "name": "r", "metric": "error", "operator": "gt", "threshold": 1,
            "notify_email": self.owner.email,
        }, format="json")
        self.assertEqual(saved.status_code, 201, saved.content)

    def test_alert_fires_for_one_rule(self):
        rule = AlertRule.objects.create(
            name="errors", metric="error", operator="gt", threshold=1,
            window_minutes=5, notify_email=self.owner.email,
        )
        Event.objects.create(name="error", value=3, timestamp=timezone.now())
        _check_rule(self.tenant, rule)
        self.assertEqual(AlertLog.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_usage_is_counted_and_stripe_event_is_idempotent(self):
        record_usage(3)
        record_usage(2)
        self.assertEqual(UsageRecord.objects.get().calls, 5)

        self.tenant.stripe_customer_id = "cus_123"
        self.tenant.subscription_status = ""
        self.tenant.save()
        with patch("apps.billing.tasks.stripe.billing.MeterEvent.create") as create:
            with override_settings(STRIPE_SECRET_KEY="sk_test"):
                report_usage_to_stripe()
        self.assertEqual(create.call_count, 0)

        self.tenant.subscription_status = "active"
        self.tenant.save()
        with patch("apps.billing.tasks.stripe.billing.MeterEvent.create") as create:
            with override_settings(STRIPE_SECRET_KEY="sk_test"):
                report_usage_to_stripe()
        self.assertEqual(create.call_count, 1)
        key = create.call_args.kwargs["idempotency_key"]
        self.assertEqual(key, f"{self.tenant.schema_name}-{timezone.now().date().isoformat()}-5")
        self.assertEqual(create.call_args.kwargs["identifier"], key)

    def test_stripe_webhook_sets_active(self):
        self.tenant.stripe_customer_id = "cus_test"
        self.tenant.subscription_status = ""
        self.tenant.save()
        _apply_event({
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_test"}},
        })
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.subscription_status, "active")

        client = APIClient(HTTP_HOST=settings.BASE_DOMAIN)
        with override_settings(STRIPE_WEBHOOK_SECRET="whsec_test"):
            rejected = client.post(
                "/api/billing/webhook/",
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1,v1=nope",
            )
        self.assertEqual(rejected.status_code, 400)

    def test_csv_formula_and_calendar_month(self):
        self.assertTrue(csv_safe("=cmd()").startswith("'"))
        Event.objects.create(name="=cmd()", value=1, timestamp=timezone.now())
        self.assertIn("'=cmd()", make_csv("daily").decode())
        start, end = report_window("monthly", now=datetime(2026, 3, 15, tzinfo=dt_timezone.utc))
        self.assertEqual((start.year, start.month, start.day), (2026, 2, 1))
        self.assertEqual((end.year, end.month, end.day), (2026, 3, 1))

    def test_admin_log_accepts_the_tenant_user(self):
        event = Event.objects.create(name="login", value=1, timestamp=timezone.now())
        LogEntry.objects.log_action(
            user_id=self.owner.pk,
            content_type_id=ContentType.objects.get_for_model(Event).pk,
            object_id=str(event.pk),
            object_repr="login",
            action_flag=ADDITION,
        )
        self.assertEqual(LogEntry.objects.get().user_id, self.owner.pk)

    def test_websocket_requires_a_tenant_session(self):
        host = self.domain.domain.encode()

        async def connect(cookie=b""):
            headers = [
                (b"host", host),
                (b"origin", b"http://" + host),
            ]
            if cookie:
                headers.append((b"cookie", cookie))
            communicator = WebsocketCommunicator(application, "/ws/metrics/", headers=headers)
            connected, _code = await communicator.connect()
            payload = None
            if connected:
                payload = await communicator.receive_json_from()
                await communicator.disconnect()
            return connected, payload

        anon_ok, _payload = async_to_sync(connect)()
        self.assertFalse(anon_ok)

        ok, payload = async_to_sync(connect)(self.ws_cookie)
        self.assertTrue(ok)
        self.assertGreaterEqual(payload["total_events"], 1)

    def test_signup_verifies_email_before_creating_a_schema(self):
        client = APIClient(HTTP_HOST=settings.BASE_DOMAIN)
        pending = client.post("/api/signup/", {
            "company": "Acme",
            "subdomain": "acme",
            "email": "a@acme.com",
            "password": "secret1234",
        }, format="json")
        self.assertEqual(pending.status_code, 202, pending.content)
        self.assertFalse(Client.objects.filter(schema_name="acme").exists())
        self.assertEqual(len(mail.outbox), 1)
        token = mail.outbox[0].body.rsplit("/api/signup/verify/", 1)[1].split("/", 1)[0]
        confirmed = client.get(f"/api/signup/verify/{token}/")
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        self.assertTrue(Client.objects.filter(schema_name="acme").exists())
        with schema_context("acme"):
            user = get_user_model().objects.get(email="a@acme.com")
            self.assertFalse(user.is_superuser)
            self.assertEqual(user.membership.role, Membership.OWNER)

    def test_owner_can_invite_a_viewer(self):
        client = self.auth_client(self.owner)
        invited = client.post("/api/users/invite/", {
            "email": "new@test.com",
            "role": "viewer",
        }, format="json")
        self.assertEqual(invited.status_code, 201, invited.content)
        user = get_user_model().objects.get(email="new@test.com")
        self.assertEqual(user.membership.role, Membership.VIEWER)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)
