from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .serializers import KakaoAuthorizationCodeSerializer
from .services import (
    KakaoAPIError,
    get_access_token_expires_at,
    exchange_authorization_code,
    fetch_kakao_profile,
    fetch_kakao_scopes,
)


REQUIRED_KAKAO_SCOPES = {
    "talk_message",
    "profile_nickname",
    "profile_image",
    "account_email",
}


class KakaoLoginView(APIView):
    """Vue에서 전달한 인가 코드로 카카오 로그인과 서비스 JWT 발급을 처리한다."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = KakaoAuthorizationCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token_data = exchange_authorization_code(
                serializer.validated_data["authorization_code"]
            )
            profile = fetch_kakao_profile(token_data["access_token"])
            scopes = fetch_kakao_scopes(token_data["access_token"])
        except (KakaoAPIError, KeyError):
            return Response(
                {"detail": "카카오 로그인 정보를 확인하지 못했습니다. 다시 시도해 주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        missing_scopes = REQUIRED_KAKAO_SCOPES.difference(scopes)
        if missing_scopes:
            return Response(
                {
                    "detail": (
                        "카카오 필수 동의 항목이 누락되었습니다: "
                        f"{', '.join(sorted(missing_scopes))}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = self._upsert_user(profile, token_data, scopes)
        except ValueError:
            return Response(
                {"detail": "카카오 닉네임, 프로필 사진, 이메일 정보를 확인할 수 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "kakao_id": user.kakao_id,
                    "nickname": user.kakao_nickname,
                    "profile_image_url": user.profile_image_url,
                },
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    @transaction.atomic
    def _upsert_user(profile, token_data, scopes):
        kakao_id = profile["id"]
        kakao_account = profile.get("kakao_account", {})
        kakao_profile = kakao_account.get("profile", {})
        nickname = kakao_profile.get("nickname", "")
        profile_image_url = kakao_profile.get("profile_image_url", "")
        email = kakao_account.get("email", "")

        if not all([nickname, profile_image_url, email]):
            raise ValueError("Required Kakao profile data is missing.")

        user, _ = User.objects.get_or_create(
            kakao_id=kakao_id,
            defaults={"username": f"kakao_{kakao_id}"},
        )
        user.kakao_nickname = nickname
        user.profile_image_url = profile_image_url
        user.email = email
        user.kakao_access_token = token_data["access_token"]
        user.kakao_refresh_token = token_data["refresh_token"]
        user.kakao_access_token_expires_at = get_access_token_expires_at(token_data)
        user.kakao_scopes = scopes
        user.save(
            update_fields=[
                "kakao_nickname",
                "profile_image_url",
                "email",
                "kakao_access_token",
                "kakao_refresh_token",
                "kakao_access_token_expires_at",
                "kakao_scopes",
            ]
        )
        return user
