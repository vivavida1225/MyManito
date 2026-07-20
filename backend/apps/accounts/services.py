import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone


logger = logging.getLogger(__name__)

KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USER_ME_URL = "https://kapi.kakao.com/v2/user/me"
KAKAO_SCOPES_URL = "https://kapi.kakao.com/v2/user/scopes"


class KakaoAPIError(Exception):
    """카카오 API 호출 실패를 서비스 계층에서 표현한다."""


def exchange_authorization_code(authorization_code):
    """인가 코드를 카카오 액세스/리프레시 토큰으로 교환한다."""
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.KAKAO_REST_API_KEY,
        "redirect_uri": settings.KAKAO_REDIRECT_URI,
        "code": authorization_code,
    }
    if settings.KAKAO_CLIENT_SECRET:
        payload["client_secret"] = settings.KAKAO_CLIENT_SECRET

    return _request_kakao_token(payload)


def fetch_kakao_profile(access_token):
    """카카오 사용자 ID와 프로필 정보를 조회한다."""
    return _request_kakao_json(
        "GET",
        KAKAO_USER_ME_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )


def fetch_kakao_scopes(access_token):
    """동의된 권한 ID만 추려 반환한다. talk_message 필수 동의 검증에 사용한다."""
    response = _request_kakao_json(
        "GET",
        KAKAO_SCOPES_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return [
        scope["id"]
        for scope in response.get("scopes", [])
        if scope.get("agreed") and scope.get("using")
    ]


def refresh_kakao_access_token(user):
    """만료됐거나 곧 만료될 카카오 액세스 토큰을 갱신해 반환한다."""
    refresh_threshold = timezone.now() + timedelta(
        seconds=settings.KAKAO_ACCESS_TOKEN_REFRESH_LEEWAY_SECONDS
    )
    if (
        user.kakao_access_token
        and user.kakao_access_token_expires_at
        and user.kakao_access_token_expires_at > refresh_threshold
    ):
        return user.kakao_access_token

    if not user.kakao_refresh_token:
        raise KakaoAPIError("저장된 카카오 리프레시 토큰이 없습니다.")

    payload = {
        "grant_type": "refresh_token",
        "client_id": settings.KAKAO_REST_API_KEY,
        "refresh_token": user.kakao_refresh_token,
    }
    if settings.KAKAO_CLIENT_SECRET:
        payload["client_secret"] = settings.KAKAO_CLIENT_SECRET

    token_data = _request_kakao_token(payload)
    user.kakao_access_token = token_data["access_token"]
    user.kakao_access_token_expires_at = get_access_token_expires_at(token_data)

    # 카카오는 리프레시 토큰을 실제로 갱신한 경우에만 해당 필드를 반환한다.
    if token_data.get("refresh_token"):
        user.kakao_refresh_token = token_data["refresh_token"]

    user.save(
        update_fields=[
            "kakao_access_token",
            "kakao_access_token_expires_at",
            "kakao_refresh_token",
        ]
    )
    return user.kakao_access_token


def _request_kakao_token(payload):
    return _request_kakao_json("POST", KAKAO_TOKEN_URL, data=payload)


def _request_kakao_json(method, url, **kwargs):
    try:
        response = requests.request(
            method,
            url,
            timeout=settings.KAKAO_REQUEST_TIMEOUT_SECONDS,
            **kwargs,
        )
    except requests.RequestException as error:
        logger.warning("Kakao API network failure: %s", error)
        raise KakaoAPIError("카카오 서버와 통신할 수 없습니다.") from error

    try:
        data = response.json()
    except ValueError as error:
        logger.warning("Kakao API returned a non-JSON response: status=%s", response.status_code)
        raise KakaoAPIError("카카오 서버의 응답 형식이 올바르지 않습니다.") from error

    if not response.ok:
        logger.warning(
            "Kakao API request failed: status=%s error=%s",
            response.status_code,
            data.get("error") or data.get("code"),
        )
        raise KakaoAPIError("카카오 인증에 실패했습니다. 다시 로그인해 주세요.")

    return data


def get_access_token_expires_at(token_data):
    try:
        expires_in = int(token_data["expires_in"])
    except (KeyError, TypeError, ValueError) as error:
        raise KakaoAPIError("카카오 토큰 만료 정보를 확인할 수 없습니다.") from error

    return timezone.now() + timedelta(seconds=expires_in)
