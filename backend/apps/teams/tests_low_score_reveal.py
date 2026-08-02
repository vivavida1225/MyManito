from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.models import Notification

from .low_score_reveal import (
    LOW_SCORE_REVEAL_EMOJIS,
    _select_low_score_participants,
    next_local_noon,
    publish_low_score_reveal,
)
from .models import Participant, Team


class LowScoreRevealTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create(
            username="low-score-owner",
            kakao_id=20001,
            kakao_nickname="관리자",
        )
        self.team = Team.objects.create(
            code="low-score-team",
            owner=self.owner,
            status=Team.Status.ACTIVE,
        )
        self.participants = []
        for index, name in enumerate(["관리자", "민지", "준호", "서연", "지우"]):
            user = self.owner if index == 0 else User.objects.create(
                username=f"low-score-member-{index}",
                kakao_id=20001 + index,
                kakao_nickname=name,
            )
            self.participants.append(
                Participant.objects.create(
                    team=self.team,
                    display_name=name,
                    claimed_by=user,
                    leaderboard_score=index + 1,
                )
            )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    @patch(
        "apps.teams.low_score_reveal.timezone.now",
        return_value=datetime(2026, 8, 2, 2, 30, tzinfo=UTC),
    )
    def test_admin_enables_reveal_for_next_local_noon(self, _now_mock):
        response = self.client.patch(
            f"/api/teams/{self.team.code}/admin/low-score-reveal/",
            {
                "enabled": True,
                "interval_days": 3,
                "percentage": 20,
                "timezone": "Asia/Seoul",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        next_at_value = response.data["low_score_reveal_next_at"]
        next_at = (
            parse_datetime(next_at_value) if isinstance(next_at_value, str) else next_at_value
        ).astimezone(ZoneInfo("Asia/Seoul"))
        self.assertEqual(next_at, datetime(2026, 8, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")))
        self.assertTrue(response.data["low_score_reveal_enabled"])
        self.assertEqual(response.data["low_score_reveal_interval_days"], 3)
        self.assertEqual(response.data["low_score_reveal_percentage"], 20)

        dashboard_response = self.client.get(f"/api/teams/{self.team.code}/admin/dashboard/")
        self.assertEqual(
            dashboard_response.data["low_score_reveal_next_at"],
            response.data["low_score_reveal_next_at"],
        )

    def test_first_reveal_uses_next_day_noon_after_local_noon(self):
        next_at = next_local_noon(
            timezone_name="Asia/Seoul",
            now=datetime(2026, 8, 2, 4, 0, tzinfo=UTC),
        )

        self.assertEqual(
            next_at.astimezone(ZoneInfo("Asia/Seoul")),
            datetime(2026, 8, 3, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        )

    def test_accepts_fifty_percent_and_rejects_invalid_settings(self):
        url = f"/api/teams/{self.team.code}/admin/low-score-reveal/"

        invalid_interval = self.client.patch(
            url,
            {"enabled": True, "interval_days": 0, "percentage": 30, "timezone": "Asia/Seoul"},
            format="json",
        )
        invalid_percentage = self.client.patch(
            url,
            {"enabled": True, "interval_days": 1, "percentage": 51, "timezone": "Asia/Seoul"},
            format="json",
        )
        invalid_timezone = self.client.patch(
            url,
            {"enabled": True, "interval_days": 1, "percentage": 30, "timezone": "Invalid/Zone"},
            format="json",
        )

        self.assertEqual(invalid_interval.status_code, 400)
        self.assertEqual(invalid_percentage.status_code, 400)
        self.assertEqual(invalid_timezone.status_code, 400)

        valid_percentage = self.client.patch(
            url,
            {"enabled": True, "interval_days": 1, "percentage": 50, "timezone": "Asia/Seoul"},
            format="json",
        )
        self.assertEqual(valid_percentage.status_code, 200)
        self.assertEqual(valid_percentage.data["low_score_reveal_percentage"], 50)

    @patch("apps.teams.low_score_reveal.publish_user_events_on_commit")
    @patch("apps.teams.low_score_reveal.send_web_push", return_value=1)
    @patch("apps.teams.low_score_reveal.random.choice", side_effect=["💀", "🚨"])
    @patch("apps.teams.low_score_reveal.random.shuffle", side_effect=lambda values: values.reverse())
    def test_due_reveal_notifies_every_claimed_participant_once(
        self,
        shuffle_mock,
        choice_mock,
        push_mock,
        realtime_mock,
    ):
        scheduled_at = datetime(2026, 8, 2, 3, 0, tzinfo=UTC)
        now = scheduled_at + timedelta(minutes=1)
        self.team.low_score_reveal_enabled = True
        self.team.low_score_reveal_interval_days = 3
        self.team.low_score_reveal_percentage = 30
        self.team.low_score_reveal_timezone = "Asia/Seoul"
        self.team.low_score_reveal_next_at = scheduled_at
        self.team.save(
            update_fields=[
                "low_score_reveal_enabled",
                "low_score_reveal_interval_days",
                "low_score_reveal_percentage",
                "low_score_reveal_timezone",
                "low_score_reveal_next_at",
            ]
        )

        result = publish_low_score_reveal(team_id=self.team.id, now=now)

        self.assertEqual(result["selected_names"], ["민지", "관리자"])
        self.assertEqual(result["notification_count"], 5)
        self.assertEqual(result["push_delivery_count"], 5)
        self.assertEqual(shuffle_mock.call_count, 2)
        self.assertEqual(choice_mock.call_count, 2)
        self.assertEqual(push_mock.call_count, 5)
        realtime_mock.assert_called_once()
        realtime_recipient_ids, realtime_event = realtime_mock.call_args.args
        self.assertEqual(set(realtime_recipient_ids), {participant.claimed_by_id for participant in self.participants})
        self.assertEqual(realtime_event, "notifications.changed")

        notifications = Notification.objects.filter(
            team=self.team,
            kind=Notification.Kind.LOW_SCORE_REVEAL,
        )
        self.assertEqual(notifications.count(), 5)
        notification = notifications.first()
        self.assertEqual(notification.title, "🚨🚨 하위 2인 공개 🚨🚨")
        self.assertEqual(
            notification.body,
            "게임 참여자들 중 활동이 저조한 2인을 공개합니다!\n"
            "다들 마니또 활동에 적극적으로 참여해 주세요!\n"
            "💀민지\n"
            "🚨관리자",
        )

        self.team.refresh_from_db()
        next_at = self.team.low_score_reveal_next_at.astimezone(ZoneInfo("Asia/Seoul"))
        self.assertEqual(next_at, datetime(2026, 8, 5, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")))

        duplicate_result = publish_low_score_reveal(team_id=self.team.id, now=now)
        self.assertIsNone(duplicate_result)
        self.assertEqual(notifications.count(), 5)

    @patch("apps.teams.low_score_reveal.random.shuffle", side_effect=lambda values: values.reverse())
    def test_cutoff_ties_are_randomized_without_exceeding_k(self, shuffle_mock):
        for participant in self.participants[:3]:
            participant.leaderboard_score = 0
        self.participants[3].leaderboard_score = 10
        self.participants[4].leaderboard_score = 20

        selected = _select_low_score_participants(self.participants, 30)

        self.assertEqual(len(selected), 2)
        self.assertTrue(set(selected).issubset(set(self.participants[:3])))
        self.assertEqual(shuffle_mock.call_count, 2)

    def test_reveal_emoji_candidates_match_current_choices(self):
        self.assertEqual(
            LOW_SCORE_REVEAL_EMOJIS,
            ("💀", "☠️"),
        )
