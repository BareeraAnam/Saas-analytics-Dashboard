from channels.db import database_sync_to_async
from channels.sessions import CookieMiddleware
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.models import Session
from django_tenants.utils import get_public_schema_name, get_tenant_domain_model, schema_context


@database_sync_to_async
def _tenant_for_host(host):
    # Domain rows live in the public schema. The socket thread must not stay
    # on whatever schema the previous request left behind.
    Domain = get_tenant_domain_model()
    with schema_context(get_public_schema_name()):
        row = Domain.objects.filter(domain=host).select_related("tenant").first()
    return row.tenant if row else None


@database_sync_to_async
def _user_for_session(schema_name, session_key):
    # Stock AuthMiddleware reads django_session from the public schema.
    # Users live in the tenant schema, so the lookup has to happen there
    # or a public user id could be treated as this tenant's user.
    if not session_key:
        return AnonymousUser()
    User = get_user_model()
    with schema_context(schema_name):
        try:
            data = Session.objects.get(session_key=session_key).get_decoded()
        except Session.DoesNotExist:
            return AnonymousUser()
        uid = data.get("_auth_user_id")
        if not uid:
            return AnonymousUser()
        try:
            return User.objects.get(pk=uid)
        except User.DoesNotExist:
            return AnonymousUser()


class TenantAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        headers = dict(scope.get("headers") or [])
        host = headers.get(b"host", b"").decode("latin1").split(":")[0]
        tenant = await _tenant_for_host(host)
        scope["tenant"] = tenant
        if tenant is None:
            scope["user"] = AnonymousUser()
        else:
            cookies = scope.get("cookies") or {}
            session_key = cookies.get(settings.SESSION_COOKIE_NAME)
            scope["user"] = await _user_for_session(tenant.schema_name, session_key)
        return await self.inner(scope, receive, send)


def TenantAuthMiddlewareStack(inner):
    # CookieMiddleware parses the Cookie header before we read the session.
    return CookieMiddleware(TenantAuthMiddleware(inner))
