from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import UsageMetric


class AnonymousUsageMetricsTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_visit_endpoint_records_only_aggregate_count(self):
        self.client.post("/api/analytics/visits/", {}, format="json")
        self.client.post("/api/analytics/visits/", {}, format="json")

        metric = UsageMetric.objects.get(date=timezone.localdate(), metric=UsageMetric.Metric.WEB_VISIT)
        self.assertEqual(metric.count, 2)
        self.assertEqual({field.name for field in UsageMetric._meta.fields}, {"id", "date", "metric", "count"})

    def test_api_requests_are_aggregated_and_visit_endpoint_is_excluded(self):
        self.client.get("/api/not-found/")

        metric = UsageMetric.objects.get(date=timezone.localdate(), metric=UsageMetric.Metric.API_REQUEST)
        self.assertEqual(metric.count, 1)
