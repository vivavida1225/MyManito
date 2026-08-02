import json
import logging
import threading

from django.conf import settings
from django.db import close_old_connections

from .models import IOSWebPushSubscription, User, WebPushDevice


logger = logging.getLogger(__name__)


def send_web_push_async(*, user_id, title, body, path):
    """웹 푸시를 요청 응답과 분리된 백그라운드 스레드에서 보낸다."""
    threading.Thread(
        target=_send_web_push_in_background,
        kwargs={"user_id": user_id, "title": title, "body": body, "path": path},
        daemon=True,
        name="mymanito-web-push",
    ).start()


def _send_web_push_in_background(*, user_id, title, body, path):
    close_old_connections()
    try:
        send_web_push(user_id=user_id, title=title, body=body, path=path)
    except Exception:
        logger.exception("Background web push delivery failed")
    finally:
        close_old_connections()


def send_web_push(*, user_id, title, body, path):
    """사용자가 선택한 기기 유형에 맞춰 FCM 또는 표준 Web Push를 보낸다."""
    if not settings.OUTBOUND_NOTIFICATIONS_ENABLED:
        return 0
    user = User.objects.filter(pk=user_id).only("id", "notification_platform").first()
    if not user:
        return 0
    if user.notification_platform == User.NotificationPlatform.IOS:
        return _send_ios_web_push(user=user, title=title, body=body, path=path)
    return _send_firebase_web_push(user_id=user.id, title=title, body=body, path=path)


def _send_firebase_web_push(*, user_id, title, body, path):
    """Android Chrome용 FCM 표시 알림을 보낸다."""
    tokens = list(WebPushDevice.objects.filter(user_id=user_id).values_list("token", flat=True))
    if not tokens or not _is_configured():
        return 0

    try:
        messaging = _get_messaging()
    except Exception as error:  # 설정 오류가 서비스의 원래 API 응답을 막지 않게 한다.
        logger.warning("Firebase web push initialization failed: %s", error)
        return 0

    sent_count = 0
    link = f"{settings.MYMANITO_APP_URL.rstrip('/')}{path}"
    for token in tokens:
        try:
            messaging.send(
                messaging.Message(
                    token=token,
                    data={"title": title, "body": body, "path": path},
                    notification=messaging.Notification(title=title, body=body),
                    webpush=messaging.WebpushConfig(
                        headers={"TTL": "86400"},
                        notification=messaging.WebpushNotification(icon="/favicon.webp"),
                        fcm_options=messaging.WebpushFCMOptions(link=link),
                    ),
                )
            )
            sent_count += 1
        except Exception as error:  # FCM 오류 종류는 SDK 버전에 따라 달라질 수 있다.
            if _is_invalid_token_error(error):
                WebPushDevice.objects.filter(token=token).delete()
            else:
                logger.warning("Firebase web push delivery failed: %s", error)
    return sent_count


def _send_ios_web_push(*, user, title, body, path):
    """홈 화면 iOS 웹앱에 표준 Web Push를 보낸다."""
    if not settings.IOS_WEB_PUSH_VAPID_PRIVATE_KEY or not settings.IOS_WEB_PUSH_VAPID_SUBJECT:
        return 0

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("iOS web push dependency is not installed")
        return 0

    sent_count = 0
    subscriptions = IOSWebPushSubscription.objects.filter(user=user)
    payload = json.dumps({"source": "mymanito", "title": title, "body": body, "path": path})
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=settings.IOS_WEB_PUSH_VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.IOS_WEB_PUSH_VAPID_SUBJECT},
                ttl=86400,
            )
            sent_count += 1
        except WebPushException as error:
            if error.response is not None and error.response.status_code in {404, 410}:
                subscription.delete()
            else:
                logger.warning("iOS web push delivery failed: %s", error)
    return sent_count


def _is_configured():
    return bool(settings.FIREBASE_SERVICE_ACCOUNT_JSON or settings.FIREBASE_SERVICE_ACCOUNT_FILE)


def _get_messaging():
    import firebase_admin
    from firebase_admin import credentials, messaging

    try:
        firebase_admin.get_app()
    except ValueError:
        if settings.FIREBASE_SERVICE_ACCOUNT_FILE:
            credential = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_FILE)
        else:
            credential = credentials.Certificate(json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON))
        firebase_admin.initialize_app(credential)
    return messaging


def _is_invalid_token_error(error):
    return error.__class__.__name__ in {"UnregisteredError", "SenderIdMismatchError"}
