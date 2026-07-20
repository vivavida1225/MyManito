from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("teams", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="planned_end_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="team",
            name="planned_end_timezone",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
