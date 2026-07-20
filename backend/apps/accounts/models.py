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

    def __str__(self):
        return self.kakao_nickname or str(self.kakao_id)
