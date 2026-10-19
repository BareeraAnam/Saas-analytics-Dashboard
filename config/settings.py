import os
import sys
from pathlib import Path

from celery.schedules import crontab
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _flag(name, default):
    # Default is the safe production choice. Callers pass "0" only for local opt-out.
    return os.getenv(name, default) == "1"


DEBUG = _flag("DEBUG", "1")
SECRET_KEY = os.getenv("SECRET_KEY", "")
# A missing key must not silently become a shared default once DEBUG is off,
# or every deployment would sign sessions with the same known value.
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key"
    else:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured("SECRET_KEY must be set when DEBUG is off.")

BASE_DOMAIN = os.getenv("BASE_DOMAIN", "localhost")
# A leading dot allows the bare domain and every tenant subdomain.
# "*" would let a client choose the Host header and aim a request at another tenant.
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = [f".{BASE_DOMAIN}"]
if DEBUG:
    # Django's test client calls the app as "testserver".
    for extra in ("testserver", "localhost", "127.0.0.1"):
        if extra not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(extra)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# Older .env files used redis://localhost:6379 with no database number.
# Strip a trailing /N so we can append our own db index below.
if REDIS_URL.rsplit("/", 1)[-1].isdigit():
    REDIS_URL = REDIS_URL.rsplit("/", 1)[0]

SHARED_APPS = [
    "daphne",
    "django_tenants",
    "apps.tenants",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "rest_framework",
    "channels",
]
# auth, sessions, admin and messages also live in each tenant schema.
# Admin's log row points at auth_user. If admin stayed only in public,
# saving in acme.localhost/admin would store Acme's user id against public.auth_user
# and Postgres would reject it.
TENANT_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    "apps.accounts",
    "apps.ingestion",
    "apps.dashboard",
    "apps.reports",
    "apps.alerts",
    "apps.billing",
]
INSTALLED_APPS = list(SHARED_APPS) + [a for a in TENANT_APPS if a not in SHARED_APPS]

TENANT_MODEL = "tenants.Client"
TENANT_DOMAIN_MODEL = "tenants.Domain"
PUBLIC_SCHEMA_URLCONF = "config.urls_public"
ROOT_URLCONF = "config.urls"

MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

DATABASES = {"default": {
    "ENGINE": "django_tenants.postgresql_backend",
    "NAME": os.getenv("DB_NAME", "analytics"),
    "USER": os.getenv("DB_USER", "analytics"),
    "PASSWORD": os.getenv("DB_PASSWORD", "analytics"),
    "HOST": os.getenv("DB_HOST", "localhost"),
    "PORT": os.getenv("DB_PORT", "5432"),
}}
DATABASE_ROUTERS = ["django_tenants.routers.TenantSyncRouter"]

# Redis is the default so cache, websocket groups and throttle counts are shared
# by Daphne and Celery. The in-memory backends are per process, so two workers
# would each keep their own cache and miss each other's socket groups.
USE_REDIS = _flag("USE_REDIS", "1")

if USE_REDIS:
    CACHES = {"default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"{REDIS_URL}/1",
        "KEY_FUNCTION": "django_tenants.cache.make_key",
        "REVERSE_KEY_FUNCTION": "django_tenants.cache.reverse_key",
    }}
    CHANNEL_LAYERS = {"default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [f"{REDIS_URL}/2"]},
    }}
else:
    CACHES = {"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "KEY_FUNCTION": "django_tenants.cache.make_key",
        "REVERSE_KEY_FUNCTION": "django_tenants.cache.reverse_key",
    }}
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

ASGI_APPLICATION = "config.asgi.application"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    # A new view that forgets permission_classes stays private.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_RATES": {
        "ingest": "600/min",
        "webhook": "600/min",
        "signup": "5/hour",
        "login": "30/hour",
        "invite": "20/hour",
    },
}

# One request must not be able to carry a million events. DRF parses the body
# into memory, so the cap is applied before the view runs.
DATA_UPLOAD_MAX_MEMORY_SIZE = 1_048_576

CELERY_BROKER_URL = f"{REDIS_URL}/0"
CELERY_RESULT_BACKEND = f"{REDIS_URL}/0"
CELERY_BEAT_SCHEDULE = {
    "check-alerts-every-minute": {"task": "apps.alerts.tasks.check_all_alerts", "schedule": 60.0},
    "daily-reports": {"task": "apps.reports.tasks.send_reports", "schedule": crontab(hour=6, minute=0), "args": ("daily",)},
    "weekly-reports": {"task": "apps.reports.tasks.send_reports", "schedule": crontab(hour=6, minute=0, day_of_week=1), "args": ("weekly",)},
    "monthly-reports": {"task": "apps.reports.tasks.send_reports", "schedule": crontab(hour=6, minute=0, day_of_month=1), "args": ("monthly",)},
    "report-usage-to-stripe": {"task": "apps.billing.tasks.report_usage_to_stripe", "schedule": crontab(minute=5)},
    "prune-old-events": {"task": "apps.ingestion.tasks.prune_old_events", "schedule": crontab(hour=3, minute=15)},
}

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_METERED_PRICE_ID = os.getenv("STRIPE_METERED_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_USE_TLS = EMAIL_PORT == 587
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER or ("reports@" + BASE_DOMAIN)

# Raw events are deleted after this many days. The dashboard only reads 24 hours,
# so keeping every row forever just makes those scans slower.
EVENT_RETENTION_DAYS = int(os.getenv("EVENT_RETENTION_DAYS", "90"))

STATIC_URL = "/static/"
LOGIN_URL = "/login/"
USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cookies and HSTS only when we are actually on HTTPS. Local DEBUG stays on HTTP.
if not DEBUG:
    SECURE_SSL_REDIRECT = _flag("SECURE_SSL_REDIRECT", "1")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    CSRF_TRUSTED_ORIGINS = [
        f"https://{BASE_DOMAIN}",
        f"https://*.{BASE_DOMAIN}",
    ]
else:
    CSRF_TRUSTED_ORIGINS = [
        f"http://{BASE_DOMAIN}",
        f"http://*.{BASE_DOMAIN}",
        f"http://{BASE_DOMAIN}:8000",
        f"http://*.{BASE_DOMAIN}:8000",
    ]

# Tests must not need a running Redis, and schema creation should not wait on a broker.
if "test" in sys.argv:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    CACHES = {"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "KEY_FUNCTION": "django_tenants.cache.make_key",
        "REVERSE_KEY_FUNCTION": "django_tenants.cache.reverse_key",
    }}
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
