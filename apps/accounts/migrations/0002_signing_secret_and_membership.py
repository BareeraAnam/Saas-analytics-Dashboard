import secrets

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def fill_api_keys(apps, schema_editor):
    # Old rows have no public id or signing secret. Generate both so the
    # column can be required. Owners need to rotate the key to learn the secret.
    APIKey = apps.get_model("accounts", "APIKey")
    for key in APIKey.objects.all():
        key.key_id = "ak_" + secrets.token_hex(8)
        key.signing_secret = secrets.token_urlsafe(32)
        key.save(update_fields=["key_id", "signing_secret"])


def grant_existing_users(apps, schema_editor):
    # Users created before roles existed keep access. Staff stay owners.
    User = apps.get_model("auth", "User")
    Membership = apps.get_model("accounts", "Membership")
    for user in User.objects.all():
        role = "owner" if user.is_superuser or user.is_staff else "member"
        Membership.objects.get_or_create(user_id=user.id, defaults={"role": role})


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="apikey",
            name="key_id",
            field=models.CharField(max_length=24, null=True),
        ),
        migrations.AddField(
            model_name="apikey",
            name="signing_secret",
            field=models.CharField(default="", max_length=80),
            preserve_default=False,
        ),
        migrations.RunPython(fill_api_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="apikey",
            name="key_id",
            field=models.CharField(max_length=24, unique=True),
        ),
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("owner", "Owner"), ("member", "Member"), ("viewer", "Viewer")], default="member", max_length=10)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="membership", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(grant_existing_users, migrations.RunPython.noop),
    ]
