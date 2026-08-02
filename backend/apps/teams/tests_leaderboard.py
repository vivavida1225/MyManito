from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User

from .leaderboard_services import generate_leaderboard_snapshot
from .models import LeaderboardSnapshot, Participant, ScoreEvent, Team
from .services import create_team_with_matching


class LeaderboardApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create(username="leader-owner", kakao_id=8100, kakao_nickname="관리자")
        self.member = User.objects.create(username="leader-member", kakao_id=8200, kakao_nickname="민지")
        self.outsider = User.objects.create(username="leader-outsider", kakao_id=8300, kakao_nickname="외부인")
        self.team = create_team_with_matching(
            owner=self.owner,
            validated_data={
                "code": "leaderboard-team",
                "rules": "",
                "reciprocal_ratio": 0,
                "is_participating": True,
                "parsed_participant_names": ["관리자", "민지", "준호"],
            },
        )
        self.member_participant = Participant.objects.get(team=self.team, display_name="민지")
        self.member_participant.claimed_by = self.member
        self.member_participant.save(update_fields=["claimed_by"])

    def test_leaderboard_exposes_only_my_score_until_results_are_released(self):
        client = APIClient()
        client.force_authenticate(self.member)
        participants = list(self.team.participants.order_by("id"))
        participants[0].leaderboard_score = 12
        participants[1].leaderboard_score = 7
        participants[2].leaderboard_score = 3
        Participant.objects.bulk_update(participants, ["leaderboard_score"])
        generate_leaderboard_snapshot(self.team)

        active_response = client.get(f"/api/teams/{self.team.code}/leaderboard/")

        self.assertEqual(active_response.status_code, 200)
        self.assertFalse(active_response.data["results_released"])
        self.assertEqual(active_response.data["my_rank"], 2)
        self.assertEqual(active_response.data["my_score"], 7)
        self.assertNotIn("민지", [entry["name"] for entry in active_response.data["entries"]])
        self.assertNotIn("leaderboard_score", str(active_response.data))
        self.assertTrue(all("score" not in entry for entry in active_response.data["entries"]))

        self.team.status = Team.Status.ENDED
        self.team.reveal_status = Team.RevealStatus.MANUAL_PENDING
        self.team.save(update_fields=["status", "reveal_status"])
        pending_response = client.get(f"/api/teams/{self.team.code}/leaderboard/")

        self.assertFalse(pending_response.data["results_released"])
        self.assertTrue(all("score" not in entry for entry in pending_response.data["entries"]))

        Participant.objects.filter(pk=self.member_participant.pk).update(leaderboard_score=17)
        self.team.reveal_status = Team.RevealStatus.MANUAL_RELEASED
        self.team.save(update_fields=["reveal_status"])
        released_response = client.get(f"/api/teams/{self.team.code}/leaderboard/")

        self.assertTrue(released_response.data["results_released"])
        self.assertIn("민지", [entry["name"] for entry in released_response.data["entries"]])
        self.assertTrue(all(entry["game_nickname"] for entry in released_response.data["entries"]))
        self.assertTrue(all("score" in entry for entry in released_response.data["entries"]))
        self.assertEqual(next(entry for entry in released_response.data["entries"] if entry["name"] == "민지")["score"], 17)

    def test_only_member_or_owner_can_read_leaderboard(self):
        client = APIClient()
        client.force_authenticate(self.outsider)

        response = client.get(f"/api/teams/{self.team.code}/leaderboard/")

        self.assertEqual(response.status_code, 403)

    @patch("apps.teams.leaderboard_services.timezone.now")
    def test_service_access_scores_all_active_teams_with_three_hour_cooldown(self, mock_now):
        first_access_at = datetime(2026, 8, 2, 3, 0, tzinfo=datetime_timezone.utc)
        mock_now.return_value = first_access_at
        second_team = create_team_with_matching(
            owner=self.member,
            validated_data={
                "code": "second-leaderboard-team",
                "rules": "",
                "reciprocal_ratio": 0,
                "is_participating": True,
                "parsed_participant_names": ["민지", "서연", "준호"],
            },
        )
        second_participant = Participant.objects.get(team=second_team, claimed_by=self.member)
        client = APIClient()
        client.force_authenticate(self.member)

        first_response = client.post("/api/teams/leaderboard/access/")
        mock_now.return_value = first_access_at + timedelta(hours=2, minutes=59)
        cooldown_response = client.post("/api/teams/leaderboard/access/")
        mock_now.return_value = first_access_at + timedelta(hours=3)
        next_response = client.post("/api/teams/leaderboard/access/")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.data["awarded_team_count"], 2)
        self.assertEqual(cooldown_response.data["awarded_team_count"], 0)
        self.assertEqual(next_response.data["awarded_team_count"], 2)
        self.member_participant.refresh_from_db()
        second_participant.refresh_from_db()
        self.assertEqual(self.member_participant.leaderboard_score, 2)
        self.assertEqual(second_participant.leaderboard_score, 2)
        self.assertEqual(ScoreEvent.objects.filter(event_type=ScoreEvent.Type.SERVICE_ACCESS).count(), 4)

    def test_snapshot_uses_tied_rank_and_stable_participant_order(self):
        participants = list(self.team.participants.order_by("id"))
        participants[0].leaderboard_score = 10
        participants[1].leaderboard_score = 10
        participants[2].leaderboard_score = 5
        Participant.objects.bulk_update(participants, ["leaderboard_score"])

        snapshot = generate_leaderboard_snapshot(self.team)

        self.assertEqual([entry["rank"] for entry in snapshot.rankings], [1, 1, 3])
        self.assertEqual([entry["participant_id"] for entry in snapshot.rankings[:2]], [participants[0].id, participants[1].id])

    def test_next_update_at_uses_three_hour_boundaries(self):
        generated_at = datetime(2026, 8, 2, 4, 20, tzinfo=datetime_timezone.utc)
        LeaderboardSnapshot.objects.filter(team=self.team).update(generated_at=generated_at)
        client = APIClient()
        client.force_authenticate(self.member)

        response = client.get(f"/api/teams/{self.team.code}/leaderboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["next_update_at"],
            datetime(2026, 8, 2, 6, 0, tzinfo=datetime_timezone.utc),
        )
