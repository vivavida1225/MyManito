from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class KakaoUserAdmin(UserAdmin):
    list_display = ("username", "kakao_id", "kakao_nickname", "email", "is_staff")
    search_fields = ("username", "kakao_id", "kakao_nickname", "email")
    fieldsets = UserAdmin.fieldsets + (
        (
            "카카오 정보",
            {
                "fields": (
                    "kakao_id",
                    "kakao_nickname",
                    "profile_image_url",
                    "kakao_access_token",
                    "kakao_refresh_token",
                    "kakao_access_token_expires_at",
                    "kakao_scopes",
                )
            },
        ),
    )
