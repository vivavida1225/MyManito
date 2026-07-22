from django.db.models import F
from django.utils import timezone

from .models import UsageMetric


def increment_usage_metric(metric):
    date = timezone.localdate()
    _usage_metric, created = UsageMetric.objects.get_or_create(
        date=date,
        metric=metric,
        defaults={"count": 1},
    )
    if not created:
        UsageMetric.objects.filter(date=date, metric=metric).update(count=F("count") + 1)
