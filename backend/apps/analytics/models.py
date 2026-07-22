from django.db import models


class UsageMetric(models.Model):
    class Metric(models.TextChoices):
        WEB_VISIT = "WEB_VISIT", "웹 방문"
        API_REQUEST = "API_REQUEST", "API 요청"

    date = models.DateField()
    metric = models.CharField(max_length=20, choices=Metric.choices)
    count = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["date", "metric"], name="unique_usage_metric_per_day"),
        ]
        ordering = ["-date", "metric"]

    def __str__(self):
        return f"{self.date} {self.metric}: {self.count}"
