from datetime import datetime, timedelta
from importlib import import_module
import json
import os
import tempfile
from unittest.mock import Mock, patch

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.teams.leaderboard_config import CHAT_LIKE_POINTS, CHAT_MESSAGE_POINTS, LEADERBOARD_NICKNAMES
from apps.teams.models import Participant, ScoreEvent, Team
from apps.teams.leaderboard_services import award_message_score
from apps.teams.services import create_team_with_matching

from .models import ChatProfile, FeedbackMessage, FeedbackMessageAttachment, FeedbackThread, Message, MessageAttachment, Notification
from .scheduler import cleanup_expired_attachments, cleanup_expired_ended_teams, cleanup_expired_notifications
from .services import make_room_id, notify_message_recipient


class ChatApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create(
            username="kakao_owner_chat",
            kakao_id=1000,
            kakao_nickname="관리자",
        )
        self.recipient_user = User.objects.create(
            username="kakao_recipient_chat",
            kakao_id=2000,
            kakao_nickname="민지",
            kakao_access_token="recipient-token",
            kakao_refresh_token="recipient-refresh-token",
            kakao_access_token_expires_at=timezone.now() + timedelta(hours=1),
        )
        self.team = create_team_with_matching(
            owner=self.owner,
            validated_data={
                "code": "chat-team",
                "rules": "익명으로 대화하기",
                "reciprocal_ratio": 0,
                "is_participating": True,
                "parsed_participant_names": ["관리자", "민지", "준호"],
            },
        )
        self.owner_participant = Participant.objects.get(team=self.team, display_name="관리자")
        self.counterpart = self.owner_participant.assigned_to
        self.counterpart.claimed_by = self.recipient_user
        self.counterpart.anonymous_nickname = "별빛"
        self.counterpart.save(update_fields=["claimed_by", "anonymous_nickname"])
        self.room_id = make_room_id(self.owner_participant.id, self.counterpart.id)

    def test_room_list_marks_unclaimed_counterparts(self):
        Message.objects.create(
            team=self.team,
            sender=self.counterpart,
            recipient=self.owner_participant,
            content="가장 최근 메시지",
        )
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.get("/api/chat/rooms/")

        self.assertEqual(response.status_code, 200)
        cared_for_room = next(room for room in response.data["rooms"] if room["room_id"] == self.room_id)
        self.assertEqual(cared_for_room["counterpart_name"], self.counterpart.display_name)
        self.assertEqual(cared_for_room["latest_message_preview"], "가장 최근 메시지")
        self.assertTrue(any(not room["counterpart_claimed"] for room in response.data["rooms"]))

    def test_room_list_uses_leaderboard_nickname_when_anonymous_nickname_is_blank(self):
        self.counterpart.anonymous_nickname = ""
        self.counterpart.save(update_fields=["anonymous_nickname"])
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.get("/api/chat/rooms/")
        room = next(
            item for item in response.data["rooms"]
            if item["room_id"] == self.room_id
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(room["counterpart_nickname"], self.counterpart.leaderboard_nickname)

    def test_room_list_reveals_counterpart_name_after_results_are_released(self):
        cared_for_me = self.owner_participant.assigned_from.get()
        self.team.status = Team.Status.ENDED
        self.team.ended_at = timezone.now()
        self.team.reveal_status = Team.RevealStatus.AUTO_RELEASED
        self.team.save(update_fields=["status", "ended_at", "reveal_status"])
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.get("/api/chat/rooms/")

        self.assertEqual(response.status_code, 200)
        room_id = make_room_id(self.owner_participant.id, cared_for_me.id)
        caring_for_me_room = next(room for room in response.data["rooms"] if room["room_id"] == room_id)
        self.assertEqual(caring_for_me_room["counterpart_name"], cared_for_me.display_name)

    def test_room_list_hides_caring_for_me_name_until_results_are_released(self):
        cared_for_me = self.owner_participant.assigned_from.get()
        caring_user = User.objects.create(
            username="kakao_caring_user",
            kakao_id=3000,
            kakao_nickname="준호",
        )
        cared_for_me.claimed_by = caring_user
        cared_for_me.anonymous_nickname = "밤하늘"
        cared_for_me.save(update_fields=["claimed_by", "anonymous_nickname"])
        ChatProfile.objects.create(
            owner=cared_for_me,
            counterpart=self.owner_participant,
            nickname="방별 밤하늘",
        )
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.get("/api/chat/rooms/")

        self.assertEqual(response.status_code, 200)
        room_id = make_room_id(self.owner_participant.id, cared_for_me.id)
        caring_for_me_room = next(room for room in response.data["rooms"] if room["room_id"] == room_id)
        self.assertTrue(caring_for_me_room["counterpart_claimed"])
        self.assertIsNone(caring_for_me_room["counterpart_name"])
        self.assertEqual(caring_for_me_room["counterpart_nickname"], "방별 밤하늘")
        self.assertNotIn(
            cared_for_me.display_name,
            json.dumps(caring_for_me_room, ensure_ascii=False, default=str),
        )

    @patch("apps.chat.services.notify_message_recipient")
    def test_send_and_poll_messages_in_an_authorized_room(self, _notify_mock):
        client = APIClient()
        client.force_authenticate(self.owner)

        send_response = client.post(
            f"/api/chat/{self.room_id}/messages/",
            {"content": "안녕하세요!"},
            format="json",
        )
        since = send_response.data["created_at"]
        poll_response = client.get(
            f"/api/chat/{self.room_id}/messages/",
            {"since": since},
        )

        self.assertEqual(send_response.status_code, 201)
        self.assertTrue(send_response.data["is_mine"])
        self.assertEqual(poll_response.status_code, 200)
        self.assertEqual(poll_response.data["messages"], [])
        self.assertEqual(poll_response.data["room"]["team_code"], self.team.code)
        self.assertEqual(
            poll_response.data["room"]["my_anonymous_nickname"],
            self.owner_participant.leaderboard_nickname,
        )

    @patch("apps.chat.services.notify_message_recipient_async")
    def test_message_response_dispatches_notifications_after_commit(self, notification_dispatch_mock):
        client = APIClient()
        client.force_authenticate(self.owner)

        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                f"/api/chat/{self.room_id}/messages/",
                {"content": "백그라운드 알림"},
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        notification_dispatch_mock.assert_called_once()

    @patch("apps.chat.services.notify_message_recipient")
    def test_ended_team_keeps_chat_available_for_seven_days(self, _notify_mock):
        Team.objects.filter(pk=self.team.pk).update(status=Team.Status.ENDED, ended_at=timezone.now())
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.post(
            f"/api/chat/{self.room_id}/messages/",
            {"content": "게임이 끝난 뒤에도 남기는 메시지"},
            format="json",
        )
        room_response = client.get(f"/api/chat/{self.room_id}/messages/")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(room_response.status_code, 200)
        self.assertEqual(room_response.data["room"]["team_status"], Team.Status.ENDED)

    def test_like_has_room_cooldown_and_is_blocked_after_game_end(self):
        client = APIClient()
        client.force_authenticate(self.owner)

        first_response = client.post(f"/api/chat/{self.room_id}/like/")
        second_response = client.post(f"/api/chat/{self.room_id}/like/")
        Team.objects.filter(pk=self.team.pk).update(status=Team.Status.ENDED, ended_at=timezone.now())
        ended_response = client.post(f"/api/chat/{self.room_id}/like/")

        self.assertEqual(first_response.status_code, 200)
        self.assertFalse(first_response.data["available"])
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.data["next_available_at"], first_response.data["next_available_at"])
        self.assertEqual(ended_response.status_code, 400)
        like_event = ScoreEvent.objects.get(event_type=ScoreEvent.Type.CHAT_LIKE)
        self.assertEqual(first_response.data["next_available_at"], like_event.created_at + timedelta(hours=3))
        self.owner_participant.refresh_from_db()
        self.assertEqual(self.owner_participant.leaderboard_score, CHAT_LIKE_POINTS)

    @patch("apps.teams.leaderboard_services.timezone.now")
    def test_message_score_obeys_cooldown_daily_limit_and_end_state(self, mock_now):
        mock_now.return_value = timezone.make_aware(datetime(2026, 7, 21, 12, 0))
        caregiver = self.owner_participant
        cared_for = caregiver.assigned_to
        room_id = make_room_id(caregiver.id, cared_for.id)
        now = timezone.now()

        for index in range(15):
            message = Message.objects.create(
                team=self.team,
                sender=cared_for,
                recipient=caregiver,
                content=f"점수 메시지 {index}",
            )
            self.assertTrue(award_message_score(message=message, room_id=room_id))
            ScoreEvent.objects.filter(source_message=message).update(created_at=now - timedelta(minutes=31))

        over_limit_message = Message.objects.create(team=self.team, sender=cared_for, recipient=caregiver, content="일일 제한")
        self.assertFalse(award_message_score(message=over_limit_message, room_id=room_id))
        cared_for.refresh_from_db()
        self.assertEqual(cared_for.leaderboard_score, CHAT_MESSAGE_POINTS * 15)

        Team.objects.filter(pk=self.team.pk).update(status=Team.Status.ENDED, ended_at=timezone.now())
        ended_message = Message.objects.create(team=self.team, sender=cared_for, recipient=caregiver, content="종료 후")
        self.assertFalse(award_message_score(message=ended_message, room_id=room_id))

    @patch("apps.chat.services.notify_message_recipient")
    def test_sends_emoticon_key_without_uploading_an_attachment(self, _notify_mock):
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.post(
            f"/api/chat/{self.room_id}/messages/",
            {"emoticon_key": "mani-0"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["emoticon_key"], "mani-0")
        self.assertFalse(MessageAttachment.objects.filter(message_id=response.data["id"]).exists())

    def test_hides_chat_rooms_after_the_seven_day_retention_period(self):
        Team.objects.filter(pk=self.team.pk).update(
            status=Team.Status.ENDED,
            ended_at=timezone.now() - timedelta(days=7, seconds=1),
        )
        client = APIClient()
        client.force_authenticate(self.owner)

        list_response = client.get("/api/chat/rooms/")
        room_response = client.get(f"/api/chat/{self.room_id}/messages/")

        self.assertEqual(list_response.status_code, 200)
        self.assertFalse(any(room["room_id"] == self.room_id for room in list_response.data["rooms"]))
        self.assertEqual(room_response.status_code, 403)

    def test_room_rejects_user_who_did_not_claim_a_participant(self):
        outsider = User.objects.create(
            username="kakao_outsider_chat",
            kakao_id=3000,
            kakao_nickname="외부인",
        )
        client = APIClient()
        client.force_authenticate(outsider)

        response = client.get(f"/api/chat/{self.room_id}/messages/")

        self.assertEqual(response.status_code, 403)

    def test_chat_profile_is_private_to_the_room_direction(self):
        client = APIClient()
        client.force_authenticate(self.owner)

        update_response = client.patch(
            f"/api/chat/{self.room_id}/profile/",
            {"nickname": "달빛", "avatar_key": "moon"},
            format="json",
        )
        profile_response = client.get(f"/api/chat/{self.room_id}/profile/")

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data["my_profile"]["nickname"], "달빛")
        self.assertNotIn(
            self.owner_participant.leaderboard_nickname,
            update_response.data["my_profile"]["nickname_options"],
        )
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.data["my_profile"]["avatar_key"], "moon")
        self.assertTrue(
            ChatProfile.objects.filter(owner=self.owner_participant, counterpart=self.counterpart).exists()
        )

    def test_chat_profile_returns_blank_when_no_nickname_is_set(self):
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.get(f"/api/chat/{self.room_id}/profile/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["my_profile"]["nickname"], "")
        nickname_options = response.data["my_profile"]["nickname_options"]
        self.assertEqual(
            nickname_options,
            [
                nickname
                for nickname in LEADERBOARD_NICKNAMES
                if nickname != self.owner_participant.leaderboard_nickname
            ],
        )
        self.assertNotIn(self.owner_participant.leaderboard_nickname, nickname_options)
        self.assertNotIn("nickname_options", response.data["counterpart_profile"])
        profile_payload = json.dumps(response.data, ensure_ascii=False, default=str)
        self.assertNotIn(self.owner_participant.display_name, profile_payload)
        self.assertNotIn(self.counterpart.display_name, profile_payload)

    @patch("apps.chat.services.notify_message_recipient_async")
    def test_room_profile_nickname_is_used_in_list_and_messages(self, _notify_mock):
        ChatProfile.objects.create(
            owner=self.counterpart,
            counterpart=self.owner_participant,
            nickname="달빛",
        )
        client = APIClient()
        client.force_authenticate(self.owner)

        rooms_response = client.get("/api/chat/rooms/")
        room = next(
            item for item in rooms_response.data["rooms"]
            if item["room_id"] == self.room_id
        )

        client.force_authenticate(self.recipient_user)
        send_response = client.post(
            f"/api/chat/{self.room_id}/messages/",
            {"content": "방별 닉네임으로 보이는 메시지"},
            format="json",
        )
        client.force_authenticate(self.owner)
        messages_response = client.get(f"/api/chat/{self.room_id}/messages/")

        self.assertEqual(rooms_response.status_code, 200)
        self.assertEqual(room["counterpart_nickname"], "달빛")
        self.assertEqual(send_response.status_code, 201)
        self.assertEqual(messages_response.status_code, 200)
        self.assertEqual(messages_response.data["messages"][0]["sender_nickname"], "달빛")
        self.assertNotIn(
            self.counterpart.display_name,
            json.dumps(messages_response.data, ensure_ascii=False, default=str),
        )

    @patch("apps.chat.services.notify_message_recipient")
    def test_message_creates_notification_that_can_be_marked_read(self, _notify_mock):
        sender_client = APIClient()
        sender_client.force_authenticate(self.owner)
        sender_client.post(
            f"/api/chat/{self.room_id}/messages/",
            {"content": "알림 확인"},
            format="json",
        )

        recipient_client = APIClient()
        recipient_client.force_authenticate(self.recipient_user)
        list_response = recipient_client.get("/api/notifications/")
        notification_id = list_response.data["notifications"][0]["id"]
        read_response = recipient_client.post(f"/api/notifications/{notification_id}/read/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data["notifications"][0]["kind"], Notification.Kind.MESSAGE)
        self.assertEqual(read_response.status_code, 204)
        self.assertTrue(Notification.objects.get(pk=notification_id).is_read)

    def test_opening_room_marks_only_that_rooms_messages_and_notifications_as_read(self):
        incoming_message = Message.objects.create(
            team=self.team,
            sender=self.counterpart,
            recipient=self.owner_participant,
            content="방에 들어가면 읽는 메시지",
        )
        room_notifications = [
            Notification.objects.create(
                recipient=self.owner,
                team=self.team,
                message=incoming_message,
                kind=Notification.Kind.MESSAGE,
                title=f"같은 방 알림 {index}",
                data={"room_id": self.room_id},
            )
            for index in range(2)
        ]
        unrelated_notification = Notification.objects.create(
            recipient=self.owner,
            team=self.team,
            kind=Notification.Kind.MESSAGE,
            title="다른 방 알림",
            data={"room_id": "999-1000"},
        )
        other_users_notification = Notification.objects.create(
            recipient=self.recipient_user,
            team=self.team,
            message=incoming_message,
            kind=Notification.Kind.MESSAGE,
            title="다른 사용자 알림",
            data={"room_id": self.room_id},
        )
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.get(f"/api/chat/{self.room_id}/messages/")

        self.assertEqual(response.status_code, 200)
        incoming_message.refresh_from_db()
        self.assertIsNotNone(incoming_message.read_at)
        self.assertFalse(
            Notification.objects.filter(
                pk__in=[notification.pk for notification in room_notifications],
                is_read=False,
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                pk__in=[notification.pk for notification in room_notifications],
                read_at__isnull=True,
            ).exists()
        )
        unrelated_notification.refresh_from_db()
        other_users_notification.refresh_from_db()
        self.assertFalse(unrelated_notification.is_read)
        self.assertFalse(other_users_notification.is_read)

    def test_room_read_endpoint_is_idempotent(self):
        incoming_message = Message.objects.create(
            team=self.team,
            sender=self.counterpart,
            recipient=self.owner_participant,
            content="실시간 수신 메시지",
        )
        Notification.objects.create(
            recipient=self.owner,
            team=self.team,
            message=incoming_message,
            kind=Notification.Kind.MESSAGE,
            title="실시간 알림",
            data={"room_id": self.room_id},
        )
        client = APIClient()
        client.force_authenticate(self.owner)

        first_response = client.post(f"/api/chat/{self.room_id}/read/")
        second_response = client.post(f"/api/chat/{self.room_id}/read/")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.data["marked_message_count"], 1)
        self.assertEqual(first_response.data["marked_notification_count"], 1)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.data["marked_message_count"], 0)
        self.assertEqual(second_response.data["marked_notification_count"], 0)

    def test_room_read_endpoint_rejects_an_outsider_without_marking_notifications(self):
        notification = Notification.objects.create(
            recipient=self.owner,
            team=self.team,
            kind=Notification.Kind.MESSAGE,
            title="접근할 수 없는 방 알림",
            data={"room_id": self.room_id},
        )
        outsider = User.objects.create(username="chat-outsider", kakao_id=2999)
        client = APIClient()
        client.force_authenticate(outsider)

        response = client.post(f"/api/chat/{self.room_id}/read/")

        self.assertEqual(response.status_code, 403)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_marks_only_my_unread_notifications_as_read(self):
        Notification.objects.create(
            recipient=self.recipient_user,
            team=self.team,
            kind=Notification.Kind.MESSAGE,
            title="첫 알림",
        )
        other_notification = Notification.objects.create(
            recipient=self.owner,
            team=self.team,
            kind=Notification.Kind.MESSAGE,
            title="다른 사용자 알림",
        )
        client = APIClient()
        client.force_authenticate(self.recipient_user)

        response = client.post("/api/notifications/read-all/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["marked_count"], 1)
        self.assertFalse(Notification.objects.filter(recipient=self.recipient_user, is_read=False).exists())
        self.assertFalse(Notification.objects.get(pk=other_notification.pk).is_read)

    def test_clears_only_my_notifications(self):
        Notification.objects.create(
            recipient=self.recipient_user,
            team=self.team,
            kind=Notification.Kind.MESSAGE,
            title="내 알림",
        )
        other_notification = Notification.objects.create(
            recipient=self.owner,
            team=self.team,
            kind=Notification.Kind.MESSAGE,
            title="다른 사용자 알림",
        )
        client = APIClient()
        client.force_authenticate(self.recipient_user)

        response = client.delete("/api/notifications/clear/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["deleted_count"], 1)
        self.assertFalse(Notification.objects.filter(recipient=self.recipient_user).exists())
        self.assertTrue(Notification.objects.filter(pk=other_notification.pk).exists())


class KakaoNotificationTests(TestCase):
    @patch("apps.chat.services.requests.post")
    @patch("apps.chat.services.refresh_kakao_access_token", return_value="valid-access-token")
    def test_marks_message_when_kakao_notification_succeeds(self, _refresh_mock, mock_post):
        mock_post.return_value = Mock(ok=True, status_code=200)
        sender = User.objects.create(username="sender", kakao_id=4000, kakao_nickname="보낸이")
        recipient = User.objects.create(
            username="recipient",
            kakao_id=5000,
            kakao_nickname="받는이",
            kakao_scopes=["talk_message"],
            kakao_access_token="recipient-token",
            kakao_refresh_token="recipient-refresh-token",
        )
        team = create_team_with_matching(
            owner=sender,
            validated_data={
                "code": "notification-team",
                "rules": "",
                "reciprocal_ratio": 100,
                "is_participating": True,
                "parsed_participant_names": ["보낸이", "받는이"],
            },
        )
        sender_participant = Participant.objects.get(team=team, display_name="보낸이")
        recipient_participant = Participant.objects.get(team=team, display_name="받는이")
        recipient_participant.claimed_by = recipient
        recipient_participant.save(update_fields=["claimed_by"])
        message = Message.objects.create(
            team=team,
            sender=sender_participant,
            recipient=recipient_participant,
            content="새 메시지",
        )

        with self.settings(MYMANITO_APP_URL="https://mymanito.wara.synology.me"):
            result = notify_message_recipient(message.id)

        message.refresh_from_db()
        self.assertTrue(result)
        self.assertIsNotNone(message.kakao_notified_at)
        template = json.loads(mock_post.call_args.kwargs["data"]["template_object"])
        self.assertIn("익명 마니또", template["text"])
        expected_chat_url = f"https://mymanito.wara.synology.me/chat/{make_room_id(sender_participant.id, recipient_participant.id)}"
        self.assertEqual(template["link"]["web_url"], expected_chat_url)
        self.assertEqual(template["link"]["mobile_web_url"], expected_chat_url)

    @patch("apps.chat.services.requests.post")
    def test_skips_kakao_notification_without_talk_message_consent(self, mock_post):
        sender = User.objects.create(username="sender-no-consent", kakao_id=4001, kakao_nickname="보낸이")
        recipient = User.objects.create(username="recipient-no-consent", kakao_id=5001, kakao_nickname="받는이")
        team = create_team_with_matching(
            owner=sender,
            validated_data={
                "code": "notification-no-consent-team",
                "rules": "",
                "reciprocal_ratio": 100,
                "is_participating": True,
                "parsed_participant_names": ["보낸이", "받는이"],
            },
        )
        sender_participant = Participant.objects.get(team=team, display_name="보낸이")
        recipient_participant = Participant.objects.get(team=team, display_name="받는이")
        recipient_participant.claimed_by = recipient
        recipient_participant.save(update_fields=["claimed_by"])
        message = Message.objects.create(
            team=team,
            sender=sender_participant,
            recipient=recipient_participant,
            content="새 메시지",
        )

        self.assertFalse(notify_message_recipient(message.id))
        mock_post.assert_not_called()


class FeedbackChatTests(TestCase):
    def setUp(self):
        self.developer = User.objects.create(id=1, username="developer", kakao_id=1, kakao_nickname="개발자")
        self.user = User.objects.create(username="feedback-user", kakao_id=9001, kakao_nickname="피드백 사용자")
        self.user_client = APIClient()
        self.user_client.force_authenticate(self.user)
        self.developer_client = APIClient()
        self.developer_client.force_authenticate(self.developer)

    @patch("apps.chat.services.send_web_push_async")
    def test_user_and_developer_can_exchange_persistent_feedback_messages(self, _push_mock):
        create_response = self.user_client.post("/api/chat/feedback/")

        self.assertEqual(create_response.status_code, 201)
        thread_id = create_response.data["thread_id"]
        send_response = self.user_client.post(
            f"/api/chat/feedback/{thread_id}/messages/",
            {"content": "알림 화면 의견입니다."},
            format="json",
        )

        self.assertEqual(send_response.status_code, 201)
        self.assertTrue(FeedbackThread.objects.filter(pk=thread_id, user=self.user, developer=self.developer).exists())
        feedback_message = FeedbackMessage.objects.get(thread_id=thread_id, content="알림 화면 의견입니다.")
        notification = Notification.objects.get(feedback_message=feedback_message)
        self.assertEqual(notification.recipient, self.developer)
        self.assertEqual(notification.kind, Notification.Kind.FEEDBACK_MESSAGE)
        self.assertIsNone(notification.team_id)
        self.assertEqual(notification.data, {"feedback_thread_id": thread_id})

        notification_response = self.developer_client.get("/api/notifications/")
        self.assertEqual(notification_response.status_code, 200)
        self.assertIsNone(notification_response.data["notifications"][0]["team_code"])
        self.assertEqual(
            notification_response.data["notifications"][0]["feedback_message_id"],
            feedback_message.id,
        )

        room_response = self.developer_client.get("/api/chat/rooms/")
        user_room_response = self.user_client.get("/api/chat/rooms/")
        messages_response = self.developer_client.get(f"/api/chat/feedback/{thread_id}/messages/")

        self.assertEqual(room_response.status_code, 200)
        self.assertEqual(room_response.data["feedback_rooms"][0]["thread_id"], thread_id)
        self.assertEqual(user_room_response.data["feedback_rooms"], [])
        self.assertEqual(messages_response.status_code, 200)
        self.assertEqual(messages_response.data["messages"][0]["sender_nickname"], "피드백 사용자")
        self.assertIsNotNone(FeedbackMessage.objects.get(thread_id=thread_id).read_at)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

        cleanup_expired_ended_teams()
        self.assertTrue(FeedbackMessage.objects.filter(thread_id=thread_id).exists())

    def test_feedback_read_endpoint_is_idempotent(self):
        thread_id = self.user_client.post("/api/chat/feedback/").data["thread_id"]
        thread = FeedbackThread.objects.get(pk=thread_id)
        feedback_message = FeedbackMessage.objects.create(
            thread=thread,
            sender=self.user,
            content="실시간 피드백",
        )
        Notification.objects.create(
            recipient=self.developer,
            feedback_message=feedback_message,
            kind=Notification.Kind.FEEDBACK_MESSAGE,
            title="새 개발자 피드백",
            data={"feedback_thread_id": thread_id},
        )

        first_response = self.developer_client.post(f"/api/chat/feedback/{thread_id}/read/")
        second_response = self.developer_client.post(f"/api/chat/feedback/{thread_id}/read/")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.data["marked_message_count"], 1)
        self.assertEqual(first_response.data["marked_notification_count"], 1)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.data["marked_message_count"], 0)
        self.assertEqual(second_response.data["marked_notification_count"], 0)

    def test_feedback_read_endpoint_rejects_an_outsider_without_marking_notifications(self):
        thread_id = self.user_client.post("/api/chat/feedback/").data["thread_id"]
        thread = FeedbackThread.objects.get(pk=thread_id)
        feedback_message = FeedbackMessage.objects.create(
            thread=thread,
            sender=self.user,
            content="외부인이 읽으면 안 되는 피드백",
        )
        notification = Notification.objects.create(
            recipient=self.developer,
            feedback_message=feedback_message,
            kind=Notification.Kind.FEEDBACK_MESSAGE,
            title="새 개발자 피드백",
            data={"feedback_thread_id": thread_id},
        )
        outsider = User.objects.create(username="feedback-outsider", kakao_id=9002)
        outsider_client = APIClient()
        outsider_client.force_authenticate(outsider)

        response = outsider_client.post(f"/api/chat/feedback/{thread_id}/read/")

        self.assertEqual(response.status_code, 403)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    @patch("apps.chat.services.send_web_push_async")
    def test_feedback_messages_support_images_and_emoticons(self, _push_mock):
        thread_id = self.user_client.post("/api/chat/feedback/").data["thread_id"]
        image = SimpleUploadedFile(
            "feedback.gif",
            b"GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\n\x00\x01\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
            content_type="image/gif",
        )

        image_response = self.user_client.post(
            f"/api/chat/feedback/{thread_id}/messages/",
            {"image": image},
            format="multipart",
        )
        emoticon_response = self.user_client.post(
            f"/api/chat/feedback/{thread_id}/messages/",
            {"emoticon_key": "mani-0"},
            format="json",
        )

        self.assertEqual(image_response.status_code, 201)
        self.assertTrue(image_response.data["image_url"])
        self.assertEqual(emoticon_response.status_code, 201)
        self.assertEqual(emoticon_response.data["emoticon_key"], "mani-0")
        self.assertEqual(FeedbackMessageAttachment.objects.filter(message_id=image_response.data["id"]).count(), 1)
        self.assertEqual(
            self.developer_client.get("/api/chat/rooms/").data["feedback_rooms"][0]["latest_message_preview"],
            "이모티콘을 보냈어요.",
        )

    @patch("apps.chat.services.requests.post")
    def test_skips_kakao_notification_when_user_disabled_it(self, mock_post):
        sender = User.objects.create(username="sender-disabled", kakao_id=4002, kakao_nickname="보낸이")
        recipient = User.objects.create(
            username="recipient-disabled",
            kakao_id=5002,
            kakao_nickname="받는이",
            kakao_scopes=["talk_message"],
            kakao_notification_enabled=False,
        )
        team = create_team_with_matching(
            owner=sender,
            validated_data={
                "code": "notification-disabled-team",
                "rules": "",
                "reciprocal_ratio": 100,
                "is_participating": True,
                "parsed_participant_names": ["보낸이", "받는이"],
            },
        )
        sender_participant = Participant.objects.get(team=team, display_name="보낸이")
        recipient_participant = Participant.objects.get(team=team, display_name="받는이")
        recipient_participant.claimed_by = recipient
        recipient_participant.save(update_fields=["claimed_by"])
        message = Message.objects.create(
            team=team,
            sender=sender_participant,
            recipient=recipient_participant,
            content="새 메시지",
        )

        self.assertFalse(notify_message_recipient(message.id))
        mock_post.assert_not_called()


class ChatCleanupSchedulerTests(TestCase):
    def test_deletes_image_file_and_attachment_after_read_for_twenty_four_hours(self):
        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            owner = User.objects.create(username="cleanup-owner", kakao_id=6000, kakao_nickname="보낸이")
            recipient = User.objects.create(username="cleanup-recipient", kakao_id=7000, kakao_nickname="받는이")
            team = create_team_with_matching(
                owner=owner,
                validated_data={
                    "code": "cleanup-team",
                    "rules": "",
                    "reciprocal_ratio": 100,
                    "is_participating": True,
                    "parsed_participant_names": ["보낸이", "받는이"],
                },
            )
            sender = Participant.objects.get(team=team, display_name="보낸이")
            recipient_participant = Participant.objects.get(team=team, display_name="받는이")
            message = Message.objects.create(
                team=team,
                sender=sender,
                recipient=recipient_participant,
                content="이미지",
                read_at=timezone.now() - timedelta(hours=25),
            )
            attachment = MessageAttachment.objects.create(
                message=message,
                image=SimpleUploadedFile("old.gif", b"GIF89a", content_type="image/gif"),
            )
            image_path = attachment.image.path

            deleted_count = cleanup_expired_attachments()

            self.assertEqual(deleted_count, 1)
            self.assertFalse(os.path.exists(image_path))
            self.assertFalse(MessageAttachment.objects.filter(pk=attachment.pk).exists())

    def test_keeps_ended_team_chat_images_until_the_seven_day_retention_expires(self):
        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            owner = User.objects.create(username="retention-owner", kakao_id=6100, kakao_nickname="보낸이")
            team = create_team_with_matching(
                owner=owner,
                validated_data={
                    "code": "retention-team",
                    "rules": "",
                    "reciprocal_ratio": 100,
                    "is_participating": True,
                    "parsed_participant_names": ["보낸이", "받는이"],
                },
            )
            sender = Participant.objects.get(team=team, display_name="보낸이")
            recipient = Participant.objects.get(team=team, display_name="받는이")
            message = Message.objects.create(
                team=team,
                sender=sender,
                recipient=recipient,
                content="보관할 이미지",
                read_at=timezone.now() - timedelta(hours=25),
            )
            attachment = MessageAttachment.objects.create(
                message=message,
                image=SimpleUploadedFile("retained.gif", b"GIF89a", content_type="image/gif"),
            )
            image_path = attachment.image.path
            Team.objects.filter(pk=team.pk).update(status=Team.Status.ENDED, ended_at=timezone.now())

            self.assertEqual(cleanup_expired_attachments(), 0)
            self.assertTrue(Message.objects.filter(pk=message.pk).exists())
            self.assertTrue(os.path.exists(image_path))

            Team.objects.filter(pk=team.pk).update(ended_at=timezone.now() - timedelta(days=7, seconds=1))
            self.assertEqual(cleanup_expired_ended_teams(), 1)
            self.assertFalse(Message.objects.filter(pk=message.pk).exists())
            self.assertFalse(os.path.exists(image_path))

    def test_deletes_teams_ended_over_seven_days_ago_and_releases_the_code(self):
        owner = User.objects.create(username="expired-owner", kakao_id=8000, kakao_nickname="관리자")
        expired_team = create_team_with_matching(
            owner=owner,
            validated_data={
                "code": "expired-team",
                "rules": "",
                "reciprocal_ratio": 100,
                "is_participating": True,
                "parsed_participant_names": ["관리자", "민지"],
            },
        )
        participant_ids = list(expired_team.participants.values_list("id", flat=True))
        Team.objects.filter(pk=expired_team.pk).update(
            status=Team.Status.ENDED,
            ended_at=timezone.now() - timedelta(days=7, seconds=1),
        )

        deleted_count = cleanup_expired_ended_teams()

        self.assertEqual(deleted_count, 1)
        self.assertFalse(Team.objects.filter(pk=expired_team.pk).exists())
        self.assertFalse(Participant.objects.filter(id__in=participant_ids).exists())

        recreated_team = create_team_with_matching(
            owner=owner,
            validated_data={
                "code": "expired-team",
                "rules": "",
                "reciprocal_ratio": 100,
                "is_participating": True,
                "parsed_participant_names": ["관리자", "준호"],
            },
        )
        self.assertEqual(recreated_team.code, "expired-team")

    def test_keeps_teams_ended_within_seven_days(self):
        owner = User.objects.create(username="recent-owner", kakao_id=9000, kakao_nickname="관리자")
        recent_team = create_team_with_matching(
            owner=owner,
            validated_data={
                "code": "recent-ended-team",
                "rules": "",
                "reciprocal_ratio": 100,
                "is_participating": True,
                "parsed_participant_names": ["관리자", "민지"],
            },
        )
        Team.objects.filter(pk=recent_team.pk).update(
            status=Team.Status.ENDED,
            ended_at=timezone.now() - timedelta(days=6, hours=23),
        )

        deleted_count = cleanup_expired_ended_teams()

        self.assertEqual(deleted_count, 0)
        self.assertTrue(Team.objects.filter(pk=recent_team.pk).exists())


class NotificationCleanupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="notification-cleanup-user", kakao_id=10001)

    @patch("apps.chat.scheduler.publish_user_events_on_commit")
    def test_deletes_read_and_unread_notifications_older_than_seven_days(self, publish_mock):
        old_unread = Notification.objects.create(
            recipient=self.user,
            kind=Notification.Kind.FEEDBACK_MESSAGE,
            title="오래된 미읽음 알림",
        )
        old_read = Notification.objects.create(
            recipient=self.user,
            kind=Notification.Kind.FEEDBACK_MESSAGE,
            title="오래된 읽은 알림",
            is_read=True,
            read_at=timezone.now() - timedelta(days=8),
        )
        fresh = Notification.objects.create(
            recipient=self.user,
            kind=Notification.Kind.FEEDBACK_MESSAGE,
            title="보관할 알림",
        )
        Notification.objects.filter(pk__in=[old_unread.pk, old_read.pk]).update(
            created_at=timezone.now() - timedelta(days=8)
        )
        Notification.objects.filter(pk=fresh.pk).update(created_at=timezone.now() - timedelta(days=6))

        deleted_count = cleanup_expired_notifications()

        self.assertEqual(deleted_count, 2)
        self.assertFalse(Notification.objects.filter(pk__in=[old_unread.pk, old_read.pk]).exists())
        self.assertTrue(Notification.objects.filter(pk=fresh.pk).exists())
        publish_mock.assert_called_once_with([self.user.id], "notifications.changed")

    def test_data_migration_deletes_existing_expired_notifications(self):
        expired = Notification.objects.create(
            recipient=self.user,
            kind=Notification.Kind.FEEDBACK_MESSAGE,
            title="배포 전에 쌓인 알림",
        )
        retained = Notification.objects.create(
            recipient=self.user,
            kind=Notification.Kind.FEEDBACK_MESSAGE,
            title="최근 알림",
        )
        Notification.objects.filter(pk=expired.pk).update(created_at=timezone.now() - timedelta(days=8))
        Notification.objects.filter(pk=retained.pk).update(created_at=timezone.now() - timedelta(days=6))
        migration = import_module("apps.chat.migrations.0007_generalize_notification")

        migration.delete_expired_notifications(django_apps, None)

        self.assertFalse(Notification.objects.filter(pk=expired.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=retained.pk).exists())
