from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .services import refresh_kakao_access_token


class KakaoLoginViewTests(TestCase):
    @patch(
        "apps.accounts.views.fetch_kakao_scopes",
        return_value=[
            "talk_message",
            "profile_nickname",
            "profile_image",
            "account_email",
        ],
    )
    @patch(
        "apps.accounts.views.fetch_kakao_profile",
        return_value={
            "id": 123456789,
            "kakao_account": {
                "email": "manito@example.com",
                "profile": {
                    "nickname": "마니또",
                    "profile_image_url": "https://example.com/profile.png",
                },
            },
        },
    )
    @patch(
        "apps.accounts.views.exchange_authorization_code",
        return_value={
            "access_token": "kakao-access-token",
            "refresh_token": "kakao-refresh-token",
            "expires_in": 3600,
        },
    )
    def test_issues_service_jwt_without_exposing_kakao_tokens(self, *_mocks):
        response = APIClient().post(
            "/api/accounts/kakao/login/",
            {"authorization_code": "authorization-code"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotIn("kakao_access_token", response.data)
        user = User.objects.get()
        self.assertEqual(user.kakao_nickname, "마니또")
        self.assertEqual(user.email, "manito@example.com")
        self.assertEqual(user.kakao_refresh_token, "kakao-refresh-token")

    @patch("apps.accounts.views.fetch_kakao_scopes", return_value=["talk_message"])
    @patch(
        "apps.accounts.views.fetch_kakao_profile",
        return_value={"id": 123456789},
    )
    @patch(
        "apps.accounts.views.exchange_authorization_code",
        return_value={
            "access_token": "kakao-access-token",
            "refresh_token": "kakao-refresh-token",
            "expires_in": 3600,
        },
    )
    def test_rejects_login_when_required_scopes_are_missing(self, *_mocks):
        response = APIClient().post(
            "/api/accounts/kakao/login/",
            {"authorization_code": "authorization-code"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("profile_nickname", response.data["detail"])


class KakaoRefreshTokenTests(TestCase):
    @patch("apps.accounts.services.requests.request")
    def test_refreshes_an_expired_kakao_access_token(self, mock_request):
        mock_response = Mock(ok=True, status_code=200)
        mock_response.json.return_value = {
            "access_token": "new-kakao-access-token",
            "expires_in": 3600,
        }
        mock_request.return_value = mock_response
        user = User.objects.create(
            username="kakao_123456789",
            kakao_id=123456789,
            kakao_access_token="expired-kakao-access-token",
            kakao_refresh_token="kakao-refresh-token",
            kakao_access_token_expires_at=timezone.now() - timedelta(seconds=1),
        )

        token = refresh_kakao_access_token(user)

        user.refresh_from_db()
        self.assertEqual(token, "new-kakao-access-token")
        self.assertEqual(user.kakao_access_token, "new-kakao-access-token")
        self.assertGreater(user.kakao_access_token_expires_at, timezone.now())


class ServiceJwtRefreshTests(TestCase):
    def test_issues_new_access_token_from_a_valid_refresh_token(self):
        user = User.objects.create(username="kakao_987", kakao_id=987)
        refresh_token = str(RefreshToken.for_user(user))

        response = APIClient().post(
            "/api/accounts/token/refresh/",
            {"refresh": refresh_token},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
