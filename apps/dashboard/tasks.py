from celery import shared_task
from django_tenants.utils import schema_context


@shared_task
def broadcast_tenant_summary(schema_name):
    # Runs a few seconds after a burst so the last events are not stuck
    # behind the debounce window. The summary is still computed once.
    from .services import publish_summary
    with schema_context(schema_name):
        publish_summary()
