import os
import sys
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-development-key-change-before-production",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [host for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "apps.analytics.apps.AnalyticsConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.teams.apps.TeamsConfig",
    "apps.chat.apps.ChatConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.analytics.middleware.AnonymousUsageMetricsMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = (
    {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    if "test" in sys.argv
    else {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [
                    {
                        "address": os.environ.get("CHANNEL_REDIS_URL", "redis://redis:6379/0"),
                        "socket_timeout": None,
                    }
                ]
            },
        }
    }
)

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "mymanito"),
        "USER": os.environ.get("POSTGRES_USER", "mymanito"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            "connect_timeout": int(
                os.environ.get("POSTGRES_CONNECT_TIMEOUT", "5")
            ),
        },
    }
}
if not DATABASES["default"]["PASSWORD"]:
    raise ImproperlyConfigured("POSTGRES_PASSWORD 환경변수를 설정해 주세요.")

LEGACY_SQLITE_PATH = os.environ.get("LEGACY_SQLITE_PATH", "")
if LEGACY_SQLITE_PATH:
    legacy_sqlite_path = Path(LEGACY_SQLITE_PATH).resolve()
    if not legacy_sqlite_path.is_file():
        raise ImproperlyConfigured(
            f"LEGACY_SQLITE_PATH 파일을 찾을 수 없습니다: {legacy_sqlite_path}"
        )
    DATABASES["legacy"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": f"{legacy_sqlite_path.as_uri()}?mode=ro",
        "OPTIONS": {"uri": True},
    }

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(
    os.environ.get("DJANGO_MEDIA_ROOT") or BASE_DIR / "media"
).resolve()
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY", "").strip()
if not JWT_SIGNING_KEY:
    if DEBUG or "test" in sys.argv:
        JWT_SIGNING_KEY = SECRET_KEY
    else:
        raise ImproperlyConfigured(
            "운영 환경에서는 JWT_SIGNING_KEY를 반드시 설정해야 합니다."
        )

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "SIGNING_KEY": JWT_SIGNING_KEY,
    "USER_ID_FIELD": "kakao_id",
    "USER_ID_CLAIM": "kakao_id",
}

# Kakao Developers > App settings > Platform key/Redirect URI values.
KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
KAKAO_CLIENT_SECRET = os.environ.get("KAKAO_CLIENT_SECRET", "")
KAKAO_REDIRECT_URI = os.environ.get("KAKAO_REDIRECT_URI", "")
KAKAO_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("KAKAO_REQUEST_TIMEOUT_SECONDS", "10"))
KAKAO_ACCESS_TOKEN_REFRESH_LEEWAY_SECONDS = int(
    os.environ.get("KAKAO_ACCESS_TOKEN_REFRESH_LEEWAY_SECONDS", "60")
)
MYMANITO_APP_URL = os.environ.get("MYMANITO_APP_URL", "https://mymanito.wara.synology.me")
FIREBASE_SERVICE_ACCOUNT_JSON = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")
FIREBASE_SERVICE_ACCOUNT_FILE = os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE", "")
IOS_WEB_PUSH_VAPID_PRIVATE_KEY = os.environ.get("IOS_WEB_PUSH_VAPID_PRIVATE_KEY", "")
IOS_WEB_PUSH_VAPID_SUBJECT = os.environ.get("IOS_WEB_PUSH_VAPID_SUBJECT", "")
SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "true").lower() == "true"
