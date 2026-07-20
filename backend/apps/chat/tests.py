from datetime import timedelta
import json
import os
import tempfile
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.teams.models import Participant, Team
from apps.teams.services import create_team_with_matching

from .models import ChatProfile, Message, MessageAttachment, Notification
from .scheduler import cleanup_expired_attachments, cleanup_expired_ended_teams
from .services import DEFAULT_ANONYMOUS_NICKNAMES, make_room_id, notify_message_recipient


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
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.get("/api/chat/rooms/")

        self.assertEqual(response.status_code, 200)
        cared_for_room = next(room for room in response.data["rooms"] if room["room_id"] == self.room_id)
        self.assertEqual(cared_for_room["counterpart_name"], self.counterpart.display_name)
        self.assertTrue(any(not room["counterpart_claimed"] for room in response.data["rooms"]))

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
        self.assertEqual(poll_response.data["room"]["my_anonymous_nickname"], "")

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
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.data["my_profile"]["avatar_key"], "moon")
        self.assertTrue(
            ChatProfile.objects.filter(owner=self.owner_participant, counterpart=self.counterpart).exists()
        )

    def test_chat_profile_uses_character_name_when_no_nickname_is_set(self):
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.get(f"/api/chat/{self.room_id}/profile/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(response.data["my_profile"]["nickname"], DEFAULT_ANONYMOUS_NICKNAMES)

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
