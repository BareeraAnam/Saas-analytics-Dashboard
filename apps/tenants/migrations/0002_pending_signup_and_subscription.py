from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="subscription_status",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.CreateModel(
            name="PendingSignup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("company", models.CharField(max_length=100)),
                ("subdomain", models.CharField(max_length=50, unique=True)),
                ("email", models.EmailField(max_length=254)),
                ("password_hash", models.CharField(max_length=128)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("status", models.CharField(default="pending", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
