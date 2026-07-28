from django.contrib.auth.models import update_last_login
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken

from .models import IOSWebPushSubscription, User, WebPushDevice
from .serializers import (
    IOSWebPushSubscriptionDeleteSerializer,
    IOSWebPushSubscriptionSerializer,
    KakaoAuthorizationCodeSerializer,
    NotificationSettingsSerializer,
    ServiceLogoutSerializer,
    WebPushDeviceSerializer,
)
from .services import (
    KakaoAPIError,
    get_access_token_expires_at,
    exchange_authorization_code,
    fetch_kakao_profile,
    fetch_kakao_scopes,
)


REQUIRED_KAKAO_SCOPES = {
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
        update_last_login(None, user)
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
                    "kakao_scopes": sorted(scopes),
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


class ServiceLogoutView(APIView):
    """현재 서비스 refresh JWT만 폐기한다."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ServiceLogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_refresh = serializer.validated_data["refresh"]

        try:
            token = UntypedToken(raw_refresh)
        except TokenError:
            return Response(
                {"detail": "유효하지 않은 refresh 토큰입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if token.get(api_settings.TOKEN_TYPE_CLAIM) != RefreshToken.token_type:
            return Response(
                {"detail": "refresh 토큰이 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if str(token.get(api_settings.USER_ID_CLAIM)) != str(request.user.kakao_id):
            return Response(
                {"detail": "다른 사용자의 refresh 토큰은 폐기할 수 없습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        token_jti = token.get(api_settings.JTI_CLAIM)
        if not token_jti:
            return Response(
                {"detail": "토큰 식별 정보를 확인할 수 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if BlacklistedToken.objects.filter(token__jti=token_jti).exists():
            return Response(status=status.HTTP_204_NO_CONTENT)

        try:
            RefreshToken(raw_refresh).blacklist()
        except TokenError:
            if BlacklistedToken.objects.filter(token__jti=token_jti).exists():
                return Response(status=status.HTTP_204_NO_CONTENT)
            return Response(
                {"detail": "refresh 토큰을 폐기하지 못했습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class WebPushDeviceView(APIView):
    """현재 로그인 사용자의 브라우저 FCM 토큰을 등록하거나 해제한다."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WebPushDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        WebPushDevice.objects.update_or_create(
            token=serializer.validated_data["token"],
            defaults={"user": request.user},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        serializer = WebPushDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        WebPushDevice.objects.filter(user=request.user, token=serializer.validated_data["token"]).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "notification_platform": request.user.notification_platform,
                "kakao_notification_enabled": request.user.kakao_notification_enabled,
                "has_ios_web_push_subscription": IOSWebPushSubscription.objects.filter(user=request.user).exists(),
            }
        )

    def patch(self, request):
        serializer = NotificationSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated_fields = []
        for field, value in serializer.validated_data.items():
            setattr(request.user, field, value)
            updated_fields.append(field)
        request.user.save(update_fields=updated_fields)
        return Response(
            {
                "notification_platform": request.user.notification_platform,
                "kakao_notification_enabled": request.user.kakao_notification_enabled,
            }
        )


class IOSWebPushSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = IOSWebPushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        IOSWebPushSubscription.objects.update_or_create(
            endpoint=serializer.validated_data["endpoint"],
            defaults={"user": request.user, **serializer.validated_data},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        serializer = IOSWebPushSubscriptionDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        IOSWebPushSubscription.objects.filter(
            user=request.user,
            endpoint=serializer.validated_data["endpoint"],
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
