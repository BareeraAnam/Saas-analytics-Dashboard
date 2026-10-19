from django.conf import settings
from django.core.management.base import BaseCommand
from django_tenants.utils import get_public_schema_name, get_tenant_domain_model, get_tenant_model


class Command(BaseCommand):
    help = "Create the public tenant and its domain if they are missing."

    def handle(self, *args, **options):
        Client = get_tenant_model()
        Domain = get_tenant_domain_model()
        schema = get_public_schema_name()
        tenant, created = Client.objects.get_or_create(
            schema_name=schema,
            defaults={"name": "Public"},
        )
        domain, _ = Domain.objects.get_or_create(
            domain=settings.BASE_DOMAIN,
            defaults={"tenant": tenant, "is_primary": True},
        )
        if domain.tenant_id != tenant.id:
            domain.tenant = tenant
            domain.is_primary = True
            domain.save()
        state = "created" if created else "already present"
        self.stdout.write(self.style.SUCCESS(f"Public tenant is {state} at {domain.domain}."))
