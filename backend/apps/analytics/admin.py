from django.contrib import admin

from .models import UsageMetric


@admin.register(UsageMetric)
class UsageMetricAdmin(admin.ModelAdmin):
    list_display = ("date", "metric", "count")
    list_filter = ("metric", "date")
    date_hierarchy = "date"
    ordering = ("-date", "metric")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
