import os
import sys
import asyncio

# 1. (선택) 윈도우 환경 실행 시 이벤트 루프 타임아웃 방지
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 2. 장고 환경변수 설정을 가장 먼저 수행합니다.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 3. 🔥 핵심: 장고 ASGI 앱을 먼저 초기화합니다. (이 순간 장고 설정이 완료됩니다)
from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()

# 4. 장고 초기화가 완전히 끝난 '후'에 Channels 및 커스텀 미들웨어를 불러옵니다.
from channels.routing import ProtocolTypeRouter, URLRouter
from apps.realtime.middleware import JwtAuthMiddleware
from apps.realtime.routing import websocket_urlpatterns

# 5. 최종 라우팅 구성
application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)