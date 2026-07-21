from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import User


SERVICE_SUBPROTOCOL = "mymanito-v1"


def _requested_protocols(scope):
    protocols = scope.get("subprotocols") or []
    if protocols:
        return protocols
    header = dict(scope.get("headers", [])).get(b"sec-websocket-protocol", b"")
    return [value.strip() for value in header.decode("ascii", "ignore").split(",") if value.strip()]


@database_sync_to_async
def _user_from_access_token(raw_token):
    try:
        token = AccessToken(raw_token)
        return User.objects.get(pk=token["user_id"], is_active=True)
    except (TokenError, User.DoesNotExist, KeyError):
        return AnonymousUser()


class JwtAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        protocols = _requested_protocols(scope)
        scope["realtime_protocol"] = protocols[0] if protocols else None
        scope["user"] = (
            await _user_from_access_token(protocols[1])
            if len(protocols) == 2 and protocols[0] == SERVICE_SUBPROTOCOL
            else AnonymousUser()
        )
        return await self.app(scope, receive, send)
