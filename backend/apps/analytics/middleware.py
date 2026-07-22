import logging

from .models import UsageMetric
from .services import increment_usage_metric


logger = logging.getLogger(__name__)
VISIT_PATH = "/api/analytics/visits/"


class AnonymousUsageMetricsMiddleware:
    """개인 식별 정보 없이 일별 API 요청 횟수만 집계한다."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/") and request.path != VISIT_PATH:
            try:
                increment_usage_metric(UsageMetric.Metric.API_REQUEST)
            except Exception:
                logger.exception("Anonymous API usage metric recording failed")
        return response
