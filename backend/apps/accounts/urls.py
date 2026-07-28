from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    IOSWebPushSubscriptionView,
    KakaoLoginView,
    NotificationSettingsView,
    ServiceLogoutView,
    WebPushDeviceView,
)


urlpatterns = [
    path("kakao/login/", KakaoLoginView.as_view(), name="kakao-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", ServiceLogoutView.as_view(), name="logout"),
    path("web-push-devices/", WebPushDeviceView.as_view(), name="web-push-device"),
    path("notification-settings/", NotificationSettingsView.as_view(), name="notification-settings"),
    path("ios-web-push-subscriptions/", IOSWebPushSubscriptionView.as_view(), name="ios-web-push-subscription"),
]
