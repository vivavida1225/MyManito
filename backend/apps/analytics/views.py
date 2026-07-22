from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UsageMetric
from .services import increment_usage_metric


class AnonymousVisitView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        increment_usage_metric(UsageMetric.Metric.WEB_VISIT)
        return Response(status=204)
