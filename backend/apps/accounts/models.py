from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """카카오 로그인 정보와 카카오 API 토큰을 보관하는 서비스 사용자."""

    kakao_id = models.BigIntegerField(
        unique=True,
        db_index=True,
        help_text="카카오가 발급하는 사용자 식별자",
    )
    kakao_nickname = models.CharField(
        max_length=100,
        blank=True,
        help_text="카카오 프로필 닉네임",
    )
    profile_image_url = models.URLField(
        blank=True,
        help_text="카카오 프로필 이미지 URL",
    )
    kakao_access_token = models.TextField(
        help_text="카카오 API 호출용 액세스 토큰. 프론트엔드에 반환하지 않는다.",
    )
    kakao_refresh_token = models.TextField(
        help_text="카카오 액세스 토큰 갱신용 리프레시 토큰. 프론트엔드에 반환하지 않는다.",
    )
    kakao_access_token_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="카카오 액세스 토큰 만료 시각",
    )
    kakao_scopes = models.JSONField(
        default=list,
        blank=True,
        help_text="사용자가 동의한 카카오 권한 ID 목록",
    )
    class NotificationPlatform(models.TextChoices):
        ANDROID = "ANDROID", "Android"
        IOS = "IOS", "iOS"

    notification_platform = models.CharField(
        max_length=10,
        choices=NotificationPlatform.choices,
        default=NotificationPlatform.ANDROID,
        help_text="기기 알림 발송 방식",
    )
    kakao_notification_enabled = models.BooleanField(
        default=True,
        help_text="카카오톡 나와의 채팅 알림 수신 여부",
    )

    def __str__(self):
        return self.kakao_nickname or str(self.kakao_id)


class WebPushDevice(models.Model):
    """사용자가 웹 푸시를 허용한 브라우저의 FCM 등록 토큰."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="web_push_devices")
    token = models.CharField(max_length=4096, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Web push device for {self.user_id}"


class IOSWebPushSubscription(models.Model):
    """홈 화면 iOS 웹앱의 표준 Web Push 구독 정보."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ios_web_push_subscriptions")
    endpoint = models.URLField(max_length=2048, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"iOS web push subscription for {self.user_id}"
