from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import KakaoLoginView


urlpatterns = [
    path("kakao/login/", KakaoLoginView.as_view(), name="kakao-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
