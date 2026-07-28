from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.tokens import AccessToken
from unittest.mock import patch

from apps.accounts.models import User
from apps.chat.models import FeedbackMessage, FeedbackThread, Message
from apps.chat.services import make_room_id
from apps.teams.models import Participant
from apps.teams.services import create_team_with_matching
from config.asgi import application

from .events import publish_user_events_on_commit, user_group_name


IN_MEMORY_CHANNEL_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNEL_LAYER)
class RealtimeConsumerTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create(username="realtime-user", kakao_id=1001)
        self.other_user = User.objects.create(username="other-user", kakao_id=1002)

    async def _connect(self, token, protocols=None):
        communicator = WebsocketCommunicator(
            application,
            "/ws/realtime/",
            subprotocols=protocols or ["mymanito-v1", token],
        )
        connected, subprotocol = await communicator.connect()
        return communicator, connected, subprotocol

    def access_token(self, user):
        return str(AccessToken.for_user(user))

    def test_valid_service_jwt_connects_with_protocol(self):
        async_to_sync(self._test_valid_service_jwt_connects_with_protocol)()

    async def _test_valid_service_jwt_connects_with_protocol(self):
        communicator, connected, subprotocol = await self._connect(self.access_token(self.user))
        self.assertTrue(connected)
        self.assertEqual(subprotocol, "mymanito-v1")
        await communicator.disconnect()

    def test_invalid_or_missing_service_jwt_is_rejected(self):
        async_to_sync(self._test_invalid_or_missing_service_jwt_is_rejected)()

    async def _test_invalid_or_missing_service_jwt_is_rejected(self):
        _communicator, invalid_connected, _subprotocol = await self._connect("invalid")
        _communicator, missing_protocol_connected, _subprotocol = await self._connect(
            self.access_token(self.user), protocols=["mymanito-v1"]
        )
        self.assertFalse(invalid_connected)
        self.assertFalse(missing_protocol_connected)

    def test_reused_database_id_and_retired_signing_key_are_rejected(self):
        async_to_sync(self._test_reused_database_id_and_retired_signing_key_are_rejected)()

    async def _test_reused_database_id_and_retired_signing_key_are_rejected(self):
        original_id = self.user.id
        original_token = self.access_token(self.user)
        await self.user.adelete()
        await User.objects.acreate(
            id=original_id,
            username="replacement-realtime-user",
            kakao_id=9001,
        )
        _communicator, reused_id_connected, _subprotocol = await self._connect(original_token)

        retired_backend = TokenBackend(
            algorithm="HS256",
            signing_key="retired-signing-key-with-at-least-32-bytes",
        )
        retired_token = retired_backend.encode(
            {
                "token_type": "access",
                "exp": int((timezone.now() + timedelta(minutes=5)).timestamp()),
                "iat": int(timezone.now().timestamp()),
                "jti": "retired-realtime-token-jti",
                "kakao_id": self.other_user.kakao_id,
            }
        )
        _communicator, retired_key_connected, _subprotocol = await self._connect(
            retired_token
        )

        self.assertFalse(reused_id_connected)
        self.assertFalse(retired_key_connected)

    def test_user_events_are_isolated_and_cover_realtime_event_types(self):
        async_to_sync(self._test_user_events_are_isolated_and_cover_realtime_event_types)()

    async def _test_user_events_are_isolated_and_cover_realtime_event_types(self):
        first, connected, _subprotocol = await self._connect(self.access_token(self.user))
        second, other_connected, _subprotocol = await self._connect(self.access_token(self.other_user))
        self.assertTrue(connected)
        self.assertTrue(other_connected)

        channel_layer = get_channel_layer()
        for event, data in (
            ("chat.message.created", {"room_id": "1-2"}),
            ("chat.rooms.changed", {}),
            ("notifications.changed", {}),
        ):
            await channel_layer.group_send(
                user_group_name(self.user.id),
                {"type": "realtime.event", "event": event, "data": data},
            )
            self.assertEqual(await first.receive_json_from(), {"event": event, **data})
            self.assertTrue(await second.receive_nothing())
        await first.disconnect()
        await second.disconnect()

    def test_event_is_not_sent_until_transaction_commit_callback_runs(self):
        with (
            patch("apps.realtime.events.publish_user_event") as publish,
            patch("apps.realtime.events.transaction.on_commit") as on_commit,
        ):
            publish_user_events_on_commit([self.user.id], "notifications.changed")
            on_commit.assert_called_once()
            publish.assert_not_called()
            on_commit.call_args.args[0]()
            publish.assert_called_once_with(self.user.id, "notifications.changed")


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNEL_LAYER)
class RealtimeChatMessageTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.developer = User.objects.create(
            username="developer",
            kakao_id=1,
            kakao_nickname="개발자",
        )
        self.assertEqual(self.developer.id, 1)
        self.sender = User.objects.create(
            username="realtime-sender",
            kakao_id=2001,
            kakao_nickname="보낸이",
        )
        self.recipient = User.objects.create(
            username="realtime-recipient",
            kakao_id=2002,
            kakao_nickname="받는이",
        )
        self.team = create_team_with_matching(
            owner=self.sender,
            validated_data={
                "code": "realtime-chat-team",
                "rules": "실시간 채팅 테스트",
                "reciprocal_ratio": 0,
                "is_participating": True,
                "parsed_participant_names": ["보낸이", "받는이", "참여자"],
            },
        )
        sender_participant = Participant.objects.get(
            team=self.team,
            claimed_by=self.sender,
        )
        sender_participant.anonymous_nickname = "햇빛"
        sender_participant.save(update_fields=["anonymous_nickname"])
        self.counterpart = sender_participant.assigned_to
        self.counterpart.claimed_by = self.recipient
        self.counterpart.anonymous_nickname = "별빛"
        self.counterpart.save(update_fields=["claimed_by", "anonymous_nickname"])
        self.room_id = make_room_id(sender_participant.id, self.counterpart.id)
        self.feedback_thread = FeedbackThread.objects.create(
            user=self.sender,
            developer=self.developer,
        )

    def access_token(self, user):
        return str(AccessToken.for_user(user))

    async def _connect(self, user):
        communicator = WebsocketCommunicator(
            application,
            "/ws/realtime/",
            subprotocols=["mymanito-v1", self.access_token(user)],
        )
        connected, _subprotocol = await communicator.connect()
        self.assertTrue(connected)
        return communicator

    @patch("apps.chat.services.notify_message_recipient_async")
    def test_general_chat_send_broadcasts_temp_id_without_duplicate_payload(self, _notify_mock):
        async_to_sync(self._test_general_chat_send_broadcasts_temp_id_without_duplicate_payload)()

        message = Message.objects.get(content="모바일에서도 바로 보여요")
        self.assertEqual(message.sender.claimed_by_id, self.sender.id)
        self.assertEqual(message.recipient.claimed_by_id, self.recipient.id)

    async def _test_general_chat_send_broadcasts_temp_id_without_duplicate_payload(self):
        sender_socket = await self._connect(self.sender)
        recipient_socket = await self._connect(self.recipient)

        await sender_socket.send_json_to(
            {
                "event": "chat.message.send",
                "tempId": "temp-1001",
                "roomId": self.room_id,
                "content": "  모바일에서도 바로 보여요  ",
            }
        )
        sender_event = await sender_socket.receive_json_from()
        recipient_event = await recipient_socket.receive_json_from()

        self.assertEqual(sender_event["event"], "chat.message.created")
        self.assertEqual(sender_event["tempId"], "temp-1001")
        self.assertEqual(sender_event["room_id"], self.room_id)
        self.assertTrue(sender_event["message"]["is_mine"])
        self.assertEqual(sender_event["message"]["content"], "모바일에서도 바로 보여요")
        self.assertEqual(recipient_event["tempId"], "temp-1001")
        self.assertFalse(recipient_event["message"]["is_mine"])
        self.assertEqual(recipient_event["message"]["sender_nickname"], "햇빛")
        self.assertEqual(sender_event["message"]["id"], recipient_event["message"]["id"])

        await sender_socket.disconnect()
        await recipient_socket.disconnect()

    @patch("apps.chat.services.send_web_push_async")
    def test_feedback_chat_send_broadcasts_temp_id_to_both_users(self, _push_mock):
        async_to_sync(self._test_feedback_chat_send_broadcasts_temp_id_to_both_users)()

        self.assertTrue(
            FeedbackMessage.objects.filter(
                thread=self.feedback_thread,
                sender=self.sender,
                content="피드백도 즉시 보여요",
            ).exists()
        )

    async def _test_feedback_chat_send_broadcasts_temp_id_to_both_users(self):
        sender_socket = await self._connect(self.sender)
        developer_socket = await self._connect(self.developer)

        await sender_socket.send_json_to(
            {
                "event": "chat.message.send",
                "tempId": "temp-2002",
                "feedbackThreadId": str(self.feedback_thread.id),
                "content": "피드백도 즉시 보여요",
            }
        )
        sender_event = await sender_socket.receive_json_from()
        developer_event = await developer_socket.receive_json_from()

        self.assertEqual(sender_event["event"], "chat.message.created")
        self.assertEqual(sender_event["tempId"], "temp-2002")
        self.assertEqual(
            str(sender_event["feedback_thread_id"]),
            str(self.feedback_thread.id),
        )
        self.assertTrue(sender_event["message"]["is_mine"])
        self.assertEqual(developer_event["tempId"], "temp-2002")
        self.assertFalse(developer_event["message"]["is_mine"])
        self.assertEqual(developer_event["message"]["sender_nickname"], "보낸이")

        await sender_socket.disconnect()
        await developer_socket.disconnect()

    def test_invalid_room_returns_failure_for_the_pending_message(self):
        async_to_sync(self._test_invalid_room_returns_failure_for_the_pending_message)()

    async def _test_invalid_room_returns_failure_for_the_pending_message(self):
        sender_socket = await self._connect(self.sender)

        await sender_socket.send_json_to(
            {
                "event": "chat.message.send",
                "tempId": "temp-3003",
                "roomId": "999999-1000000",
                "content": "실패 처리",
            }
        )
        failure_event = await sender_socket.receive_json_from()

        self.assertEqual(failure_event["event"], "chat.message.failed")
        self.assertEqual(failure_event["tempId"], "temp-3003")
        self.assertIn("찾을 수 없습니다", failure_event["detail"])

        await sender_socket.disconnect()
