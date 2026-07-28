import logging
import re

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model

from apps.chat.services import (
    ChatRoomError,
    FeedbackError,
    create_feedback_message,
    create_message,
    get_chat_room_for_user,
    get_feedback_thread_for_user,
)

from .events import user_group_name
from .middleware import SERVICE_SUBPROTOCOL


logger = logging.getLogger(__name__)
TEMP_ID_PATTERN = re.compile(r"^temp-\d+$")


def create_realtime_chat_message(*, user_id, payload):
    user = get_user_model().objects.get(pk=user_id)
    common_arguments = {
        "content": payload["content"],
        "image": None,
        "client_temp_id": payload["tempId"],
    }
    if payload.get("roomId"):
        room = get_chat_room_for_user(room_id=payload["roomId"], user=user)
        return create_message(room=room, **common_arguments)

    thread = get_feedback_thread_for_user(
        thread_id=payload["feedbackThreadId"],
        user=user,
    )
    return create_feedback_message(thread=thread, sender=user, **common_arguments)


class RealtimeConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated or self.scope.get("realtime_protocol") != SERVICE_SUBPROTOCOL:
            await self.close(code=4401)
            return
        self.group_name = user_group_name(user.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept(subprotocol=SERVICE_SUBPROTOCOL)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        temp_id = content.get("tempId") if isinstance(content, dict) else None
        try:
            self._validate_chat_message(content)
            await database_sync_to_async(create_realtime_chat_message)(
                user_id=self.scope["user"].id,
                payload=content,
            )
        except (ChatRoomError, FeedbackError, ValueError) as error:
            await self._send_message_failure(temp_id, str(error))
        except Exception:
            logger.exception("WebSocket 채팅 메시지 저장 중 오류가 발생했습니다.")
            await self._send_message_failure(
                temp_id,
                "메시지를 보내지 못했습니다. 다시 시도해 주세요.",
            )

    async def realtime_event(self, event):
        await self.send_json({"event": event["event"], **event["data"]})

    @staticmethod
    def _validate_chat_message(content):
        if not isinstance(content, dict):
            raise ValueError("올바르지 않은 실시간 요청입니다.")
        if content.get("event") != "chat.message.send":
            raise ValueError("지원하지 않는 실시간 요청입니다.")
        temp_id = content.get("tempId")
        if not isinstance(temp_id, str) or not TEMP_ID_PATTERN.fullmatch(temp_id):
            raise ValueError("올바르지 않은 임시 메시지 ID입니다.")
        message_content = content.get("content")
        if not isinstance(message_content, str) or not message_content.strip():
            raise ValueError("메시지 내용을 입력해 주세요.")
        content["content"] = message_content.strip()
        room_targets = [content.get("roomId"), content.get("feedbackThreadId")]
        if sum(bool(target) for target in room_targets) != 1:
            raise ValueError("채팅방을 하나만 지정해 주세요.")

    async def _send_message_failure(self, temp_id, detail):
        await self.send_json(
            {
                "event": "chat.message.failed",
                "tempId": temp_id,
                "detail": detail,
            }
        )
