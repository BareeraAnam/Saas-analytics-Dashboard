import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_asgi = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.dashboard.middleware import TenantAuthMiddlewareStack  # noqa: E402
from apps.dashboard.routing import websocket_urlpatterns  # noqa: E402

# AllowedHostsOriginValidator rejects a browser Origin that is not in ALLOWED_HOSTS.
# TenantAuthMiddlewareStack then loads the session user from that tenant's schema.
# Without both, anyone could open /ws/metrics/ with another tenant's Host header.
application = ProtocolTypeRouter({
    "http": django_asgi,
    "websocket": AllowedHostsOriginValidator(
        TenantAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    ),
})
