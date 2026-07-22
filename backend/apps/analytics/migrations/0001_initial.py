from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="UsageMetric",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                (
                    "metric",
                    models.CharField(
                        choices=[("WEB_VISIT", "웹 방문"), ("API_REQUEST", "API 요청")],
                        max_length=20,
                    ),
                ),
                ("count", models.PositiveBigIntegerField(default=0)),
            ],
            options={"ordering": ["-date", "metric"]},
        ),
        migrations.AddConstraint(
            model_name="usagemetric",
            constraint=models.UniqueConstraint(fields=("date", "metric"), name="unique_usage_metric_per_day"),
        ),
    ]
