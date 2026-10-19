from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


class Client(TenantMixin):
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    # Empty until Stripe's webhook says the subscription is active.
    subscription_status = models.CharField(max_length=32, blank=True, default="")
    plan = models.CharField(max_length=20, default="free")

    auto_create_schema = True

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    pass


class PendingSignup(models.Model):
    """Signup is stored here until the email is confirmed.

    Creating the schema in the request was a denial-of-service: each call runs
    every tenant migration. That work now happens in a background task.
    """

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"

    company = models.CharField(max_length=100)
    subdomain = models.CharField(max_length=50, unique=True)
    email = models.EmailField()
    password_hash = models.CharField(max_length=128)
    token_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=20, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
