from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User

from .leaderboard_services import award_visit_score, generate_leaderboard_snapshot
from .models import Participant, ScoreEvent, Team
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

    def test_leaderboard_hides_score_until_results_are_released(self):
        client = APIClient()
        client.force_authenticate(self.member)

        active_response = client.get(f"/api/teams/{self.team.code}/leaderboard/")

        self.assertEqual(active_response.status_code, 200)
        self.assertFalse(active_response.data["results_released"])
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

    def test_visit_score_has_server_cooldown(self):
        self.assertTrue(award_visit_score(team=self.team, user=self.member))
        self.assertFalse(award_visit_score(team=self.team, user=self.member))
        self.member_participant.refresh_from_db()
        self.assertEqual(self.member_participant.leaderboard_score, 1)
        self.assertEqual(ScoreEvent.objects.filter(event_type=ScoreEvent.Type.TEAM_VISIT).count(), 1)

    def test_snapshot_uses_tied_rank_and_stable_participant_order(self):
        participants = list(self.team.participants.order_by("id"))
        participants[0].leaderboard_score = 10
        participants[1].leaderboard_score = 10
        participants[2].leaderboard_score = 5
        Participant.objects.bulk_update(participants, ["leaderboard_score"])

        snapshot = generate_leaderboard_snapshot(self.team)

        self.assertEqual([entry["rank"] for entry in snapshot.rankings], [1, 1, 3])
        self.assertEqual([entry["participant_id"] for entry in snapshot.rankings[:2]], [participants[0].id, participants[1].id])
