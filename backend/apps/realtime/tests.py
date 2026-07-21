from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import TestCase, override_settings
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch

from apps.accounts.models import User
from config.asgi import application

from .events import publish_user_events_on_commit, user_group_name


IN_MEMORY_CHANNEL_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNEL_LAYER)
class RealtimeConsumerTests(TestCase):
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
        return str(RefreshToken.for_user(user).access_token)

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
        with patch("apps.realtime.events.publish_user_event") as publish:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                publish_user_events_on_commit([self.user.id], "notifications.changed")
            self.assertEqual(len(callbacks), 1)
            publish.assert_not_called()
            callbacks[0]()
            publish.assert_called_once_with(self.user.id, "notifications.changed")
