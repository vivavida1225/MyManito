from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.analytics.views import AnonymousVisitView
from apps.chat.views import NotificationClearView, NotificationListView, NotificationReadAllView, NotificationReadView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/teams/", include("apps.teams.urls")),
    path("api/chat/", include("apps.chat.urls")),
    path("api/analytics/visits/", AnonymousVisitView.as_view(), name="analytics-visit"),
    path("api/notifications/", NotificationListView.as_view(), name="notification-list"),
    path("api/notifications/read-all/", NotificationReadAllView.as_view(), name="notification-read-all"),
    path("api/notifications/clear/", NotificationClearView.as_view(), name="notification-clear"),
    path("api/notifications/<int:notification_id>/read/", NotificationReadView.as_view(), name="notification-read"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
