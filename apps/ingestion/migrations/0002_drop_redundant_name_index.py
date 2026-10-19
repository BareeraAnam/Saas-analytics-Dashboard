from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0001_initial"),
    ]

    operations = [
        # The (name, timestamp) index already serves filters that start with name.
        migrations.AlterField(
            model_name="event",
            name="name",
            field=models.CharField(max_length=100),
        ),
    ]
