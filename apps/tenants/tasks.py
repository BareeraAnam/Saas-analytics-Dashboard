from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import transaction
from django_tenants.utils import schema_context
from celery import shared_task

from apps.accounts.models import Membership

from .models import Client, Domain, PendingSignup
from django.conf import settings


@shared_task
def provision_tenant(pending_id):
    """Create the schema outside the signup request.

    migrate_schemas runs inside Client.save. Doing that in the HTTP request
    made signup an easy way to exhaust the database.
    """
    pending = PendingSignup.objects.get(pk=pending_id)
    if pending.status == PendingSignup.DONE:
        return
    schema = pending.subdomain.replace("-", "_")
    try:
        with transaction.atomic():
            if Client.objects.filter(schema_name=schema).exists():
                pending.status = PendingSignup.DONE
                pending.save(update_fields=["status"])
                return
            tenant = Client.objects.create(schema_name=schema, name=pending.company)
            Domain.objects.create(
                domain=f"{pending.subdomain}.{settings.BASE_DOMAIN}",
                tenant=tenant,
                is_primary=True,
            )
            with schema_context(tenant.schema_name):
                User = get_user_model()
                # Staff so the owner can open Django admin. Not a superuser:
                # invited users get a role, and the owner is granted model permissions explicitly.
                user = User(
                    username=pending.email,
                    email=pending.email,
                    is_staff=True,
                    is_superuser=False,
                    password=pending.password_hash,
                )
                user.save()
                user.user_permissions.set(Permission.objects.all())
                Membership.objects.create(user=user, role=Membership.OWNER)
        pending.status = PendingSignup.DONE
        pending.save(update_fields=["status"])
    except Exception:
        pending.status = PendingSignup.FAILED
        pending.save(update_fields=["status"])
        raise
