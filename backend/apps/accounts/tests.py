from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import IOSWebPushSubscription, User, WebPushDevice
from .push import send_web_push, send_web_push_async
from .services import refresh_kakao_access_token


class KakaoLoginViewTests(TestCase):
    @patch(
        "apps.accounts.views.fetch_kakao_scopes",
        return_value=[
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
    def test_issues_service_jwt_without_talk_message_consent(self, *_mocks):
        response = APIClient().post(
            "/api/accounts/kakao/login/",
            {"authorization_code": "authorization-code"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotIn("kakao_access_token", response.data)
        self.assertNotIn("talk_message", response.data["user"]["kakao_scopes"])
        user = User.objects.get()
        access_token = AccessToken(response.data["access"])
        self.assertEqual(access_token["kakao_id"], str(user.kakao_id))
        self.assertNotIn("user_id", access_token)
        self.assertEqual(user.kakao_nickname, "마니또")
        self.assertEqual(user.email, "manito@example.com")
        self.assertEqual(user.kakao_refresh_token, "kakao-refresh-token")
        self.assertIsNotNone(user.last_login)

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
    def test_uses_short_access_and_fixed_30_day_refresh_lifetimes(self):
        self.assertEqual(api_settings.ACCESS_TOKEN_LIFETIME, timedelta(minutes=15))
        self.assertEqual(api_settings.REFRESH_TOKEN_LIFETIME, timedelta(days=30))
        self.assertFalse(api_settings.ROTATE_REFRESH_TOKENS)

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
        self.assertNotIn("refresh", response.data)
        access_token = RefreshToken(refresh_token).access_token
        self.assertEqual(access_token["kakao_id"], str(user.kakao_id))
        self.assertNotIn("user_id", access_token)

    def test_reused_database_id_does_not_authenticate_a_different_kakao_user(self):
        original_user = User.objects.create(username="original-user", kakao_id=10001)
        original_user_id = original_user.id
        access_token = str(RefreshToken.for_user(original_user).access_token)
        original_user.delete()
        replacement_user = User.objects.create(
            id=original_user_id,
            username="replacement-user",
            kakao_id=20002,
        )

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = client.get("/api/accounts/notification-settings/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(User.objects.get(pk=original_user_id), replacement_user)

    def test_rejects_access_token_signed_with_a_retired_key(self):
        user = User.objects.create(username="current-user", kakao_id=30003)
        retired_backend = TokenBackend(
            algorithm="HS256",
            signing_key="retired-signing-key-with-at-least-32-bytes",
        )
        retired_token = retired_backend.encode(
            {
                "token_type": "access",
                "exp": int((timezone.now() + timedelta(minutes=5)).timestamp()),
                "iat": int(timezone.now().timestamp()),
                "jti": "retired-token-jti",
                "kakao_id": user.kakao_id,
            }
        )

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {retired_token}")
        response = client.get("/api/accounts/notification-settings/")

        self.assertEqual(response.status_code, 401)


class ServiceLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="logout-user", kakao_id=40004)
        self.refresh = RefreshToken.for_user(self.user)
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(self.refresh.access_token)}"
        )

    def test_blacklists_refresh_token_idempotently_without_deleting_push_settings(self):
        WebPushDevice.objects.create(user=self.user, token="logout-browser-token")
        IOSWebPushSubscription.objects.create(
            user=self.user,
            endpoint="https://web.push.apple.com/logout-subscription",
            p256dh="public-key",
            auth="auth-secret",
        )

        response = self.client.post(
            "/api/accounts/logout/",
            {"refresh": str(self.refresh)},
            format="json",
        )
        repeated_response = self.client.post(
            "/api/accounts/logout/",
            {"refresh": str(self.refresh)},
            format="json",
        )
        refresh_response = APIClient().post(
            "/api/accounts/token/refresh/",
            {"refresh": str(self.refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(repeated_response.status_code, 204)
        self.assertEqual(refresh_response.status_code, 401)
        self.assertTrue(WebPushDevice.objects.filter(user=self.user).exists())
        self.assertTrue(IOSWebPushSubscription.objects.filter(user=self.user).exists())

    def test_rejects_another_users_refresh_token(self):
        other_user = User.objects.create(username="other-logout-user", kakao_id=50005)
        other_refresh = RefreshToken.for_user(other_user)

        response = self.client.post(
            "/api/accounts/logout/",
            {"refresh": str(other_refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        refresh_response = APIClient().post(
            "/api/accounts/token/refresh/",
            {"refresh": str(other_refresh)},
            format="json",
        )
        self.assertEqual(refresh_response.status_code, 200)


class WebPushDeviceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="push-user", kakao_id=500)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_registers_and_reassigns_a_browser_token_to_the_current_user(self):
        response = self.client.post(
            "/api/accounts/web-push-devices/",
            {"token": "browser-token"},
            format="json",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(WebPushDevice.objects.get(token="browser-token").user, self.user)

    @patch("apps.accounts.push._get_messaging")
    def test_sends_data_only_notification_to_registered_device(self, get_messaging_mock):
        WebPushDevice.objects.create(user=self.user, token="browser-token")
        messaging = Mock()
        messaging.Message.side_effect = lambda **kwargs: kwargs
        get_messaging_mock.return_value = messaging

        with self.settings(FIREBASE_SERVICE_ACCOUNT_JSON="{}"):
            sent_count = send_web_push(
                user_id=self.user.id,
                title="새 소식",
                body="확인해 보세요.",
                path="/notifications",
            )

        self.assertEqual(sent_count, 1)
        self.assertEqual(
            messaging.send.call_args.args[0]["data"],
            {"title": "새 소식", "body": "확인해 보세요.", "path": "/notifications"},
        )

    @patch("apps.accounts.push.threading.Thread")
    def test_dispatches_web_push_on_a_daemon_thread(self, thread_mock):
        send_web_push_async(
            user_id=self.user.id,
            title="새 소식",
            body="확인해 보세요.",
            path="/notifications",
        )

        thread_kwargs = thread_mock.call_args.kwargs
        self.assertTrue(thread_kwargs["daemon"])
        self.assertEqual(thread_kwargs["name"], "mymanito-web-push")
        self.assertEqual(
            thread_kwargs["kwargs"],
            {"user_id": self.user.id, "title": "새 소식", "body": "확인해 보세요.", "path": "/notifications"},
        )
        thread_mock.return_value.start.assert_called_once()


class NotificationSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="notification-user", kakao_id=501)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_changes_platform_kakao_setting_and_registers_an_ios_subscription(self):
        response = self.client.patch(
            "/api/accounts/notification-settings/",
            {"notification_platform": "IOS", "kakao_notification_enabled": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.notification_platform, User.NotificationPlatform.IOS)
        self.assertFalse(self.user.kakao_notification_enabled)

        response = self.client.post(
            "/api/accounts/ios-web-push-subscriptions/",
            {
                "endpoint": "https://web.push.apple.com/example-subscription",
                "p256dh": "public-key",
                "auth": "auth-secret",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(IOSWebPushSubscription.objects.get().user, self.user)

    def test_deletes_only_the_current_users_ios_subscription(self):
        other_user = User.objects.create(username="other-ios-user", kakao_id=502)
        own_subscription = IOSWebPushSubscription.objects.create(
            user=self.user,
            endpoint="https://web.push.apple.com/own-subscription",
            p256dh="own-public-key",
            auth="own-auth-secret",
        )
        other_subscription = IOSWebPushSubscription.objects.create(
            user=other_user,
            endpoint="https://web.push.apple.com/other-subscription",
            p256dh="other-public-key",
            auth="other-auth-secret",
        )

        response = self.client.delete(
            "/api/accounts/ios-web-push-subscriptions/",
            {"endpoint": own_subscription.endpoint},
            format="json",
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            IOSWebPushSubscription.objects.filter(pk=own_subscription.pk).exists()
        )
        self.assertTrue(
            IOSWebPushSubscription.objects.filter(pk=other_subscription.pk).exists()
        )

    @patch("apps.accounts.push._send_ios_web_push", return_value=1)
    @patch("apps.accounts.push._send_firebase_web_push")
    def test_uses_ios_delivery_for_an_ios_user(self, firebase_send_mock, ios_send_mock):
        self.user.notification_platform = User.NotificationPlatform.IOS
        self.user.save(update_fields=["notification_platform"])

        sent_count = send_web_push(
            user_id=self.user.id,
            title="새 소식",
            body="확인해 보세요.",
            path="/notifications",
        )

        self.assertEqual(sent_count, 1)
        ios_send_mock.assert_called_once()
        firebase_send_mock.assert_not_called()
