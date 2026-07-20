from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.models import Message

from .models import LeaderboardSnapshot, Participant, ScoreEvent, Team
from .services import create_team_with_matching
from .leaderboard_services import award_visit_score, generate_leaderboard_snapshot


class TeamMatchingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create(
            username="kakao_1",
            kakao_id=1,
            kakao_nickname="관리자",
        )

    def test_creates_a_derangement_without_reciprocal_pairs_at_zero_percent(self):
        team = create_team_with_matching(
            owner=self.owner,
            validated_data={
                "code": "summer-manito",
                "rules": "즐겁게 참여하기",
                "reciprocal_ratio": 0,
                "is_participating": True,
                "parsed_participant_names": ["관리자", "민지", "준호", "서연"],
            },
        )

        participants = list(team.participants.order_by("id"))
        reciprocal_participant_count = sum(
            1
            for participant in participants
            if participant.assigned_to.assigned_to_id == participant.id
        )

        self.assertEqual(team.status, "ACTIVE")
        self.assertEqual(len(participants), 4)
        self.assertTrue(all(p.assigned_to_id != p.id for p in participants))
        self.assertEqual(reciprocal_participant_count, 0)
        self.assertEqual(
            Participant.objects.get(team=team, display_name="관리자").claimed_by,
            self.owner,
        )
        self.assertTrue(all(participant.leaderboard_nickname for participant in participants))
        self.assertTrue(all(participant.leaderboard_avatar_key for participant in participants))
        self.assertEqual(len({participant.leaderboard_nickname for participant in participants}), len(participants))
        self.assertTrue(
            all(
                participant.leaderboard_nickname.endswith("마니")
                == participant.leaderboard_avatar_key.startswith("mani-")
                for participant in participants
            )
        )
        self.assertTrue(LeaderboardSnapshot.objects.filter(team=team).exists())

    def test_authenticated_api_creates_team(self):
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.post(
            "/api/teams/",
            {
                "code": "api-manito",
                "rules": "즐겁게 참여하기",
                "reciprocal_ratio": 20,
                "is_participating": True,
                "participant_names": "관리자, 민지\n준호 서연",
                "reveal_mode": "ADMIN",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["participant_count"], 4)
        self.assertEqual(response.data["reveal_mode"], Team.RevealMode.ADMIN)

    def test_two_person_team_requires_one_hundred_percent_reciprocal_ratio(self):
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.post(
            "/api/teams/",
            {
                "code": "two-person-team",
                "reciprocal_ratio": 20,
                "is_participating": True,
                "participant_names": "관리자, 민지",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("reciprocal_ratio", response.data)


class TeamParticipationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create(
            username="kakao_owner",
            kakao_id=100,
            kakao_nickname="관리자",
        )
        self.member = User.objects.create(
            username="kakao_member",
            kakao_id=200,
            kakao_nickname="민지",
        )
        self.other_member = User.objects.create(
            username="kakao_other_member",
            kakao_id=300,
            kakao_nickname="준호",
        )
        self.team = create_team_with_matching(
            owner=self.owner,
            validated_data={
                "code": "joinable-team",
                "rules": "서로 친절하게 대화하기",
                "reciprocal_ratio": 0,
                "is_participating": False,
                "parsed_participant_names": ["민지", "준호", "서연"],
            },
        )

    def test_team_detail_hides_participants_and_assignments(self):
        client = APIClient()
        client.force_authenticate(self.member)

        response = client.get(f"/api/teams/{self.team.code}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rules"], "서로 친절하게 대화하기")
        self.assertNotIn("participants", response.data)
        self.assertNotIn("assigned_to", response.data)

    def test_claim_returns_only_my_assigned_target_and_prevents_second_claim(self):
        client = APIClient()
        client.force_authenticate(self.member)
        minji = Participant.objects.get(team=self.team, display_name="민지")
        junho = Participant.objects.get(team=self.team, display_name="준호")

        first_response = client.post(
            f"/api/teams/{self.team.code}/claim/",
            {"participant_id": minji.id},
            format="json",
        )
        second_response = client.post(
            f"/api/teams/{self.team.code}/claim/",
            {"participant_id": junho.id},
            format="json",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.data["participant"]["display_name"], "민지")
        self.assertIn("display_name", first_response.data["assigned_to"])
        self.assertEqual(second_response.status_code, 400)

    def test_existing_claim_can_retrieve_only_own_assignment(self):
        client = APIClient()
        client.force_authenticate(self.member)
        minji = Participant.objects.get(team=self.team, display_name="민지")

        client.post(
            f"/api/teams/{self.team.code}/claim/",
            {"participant_id": minji.id},
            format="json",
        )
        response = client.get(f"/api/teams/{self.team.code}/my-assignment/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_claimed"])
        self.assertEqual(response.data["participant"]["display_name"], "민지")
        self.assertIn("display_name", response.data["assigned_to"])

    def test_unclaimed_user_cannot_retrieve_an_assignment(self):
        client = APIClient()
        client.force_authenticate(self.member)

        response = client.get(f"/api/teams/{self.team.code}/my-assignment/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_claimed"])
        self.assertNotIn("assigned_to", response.data)

    def test_claimed_name_cannot_be_claimed_by_another_user(self):
        client = APIClient()
        minji = Participant.objects.get(team=self.team, display_name="민지")

        client.force_authenticate(self.member)
        first_response = client.post(
            f"/api/teams/{self.team.code}/claim/",
            {"participant_id": minji.id},
            format="json",
        )
        client.force_authenticate(self.other_member)
        second_response = client.post(
            f"/api/teams/{self.team.code}/claim/",
            {"participant_id": minji.id},
            format="json",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 400)

    def test_claimed_participant_can_save_anonymous_nickname(self):
        client = APIClient()
        client.force_authenticate(self.member)
        minji = Participant.objects.get(team=self.team, display_name="민지")
        client.post(
            f"/api/teams/{self.team.code}/claim/",
            {"participant_id": minji.id},
            format="json",
        )

        response = client.post(
            f"/api/teams/{self.team.code}/anonymous-nickname/",
            {"anonymous_nickname": "별빛"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        minji.refresh_from_db()
        self.assertEqual(minji.anonymous_nickname, "별빛")


class TeamAdminLifecycleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create(
            username="kakao_admin",
            kakao_id=900,
            kakao_nickname="관리자",
        )
        self.team = create_team_with_matching(
            owner=self.owner,
            validated_data={
                "code": "admin-team",
                "rules": "즐겁게 참여하기",
                "reciprocal_ratio": 0,
                "is_participating": True,
                "parsed_participant_names": ["관리자", "민지", "준호"],
            },
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_dashboard_returns_progress_and_reset_claim(self):
        minji = Participant.objects.get(team=self.team, display_name="민지")
        member = User.objects.create(username="kakao_admin_member", kakao_id=901, kakao_nickname="민지")
        minji.claimed_by = member
        minji.save(update_fields=["claimed_by"])
        dashboard_response = self.client.get(
            f"/api/teams/{self.team.code}/admin/dashboard/",
        )
        reset_response = self.client.post(
            f"/api/teams/{self.team.code}/admin/reset-claim/",
            {"participant_id": minji.id},
            format="json",
        )

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(dashboard_response.data["claimed_count"], 2)
        self.assertEqual(reset_response.status_code, 204)
        minji.refresh_from_db()
        self.assertIsNone(minji.claimed_by)

    def test_my_teams_lists_owned_team_with_dashboard_card_data(self):
        response = self.client.get("/api/teams/mine/")

        self.assertEqual(response.status_code, 200)
        team_data = response.data["teams"][0]
        self.assertEqual(team_data["code"], self.team.code)
        self.assertTrue(team_data["is_owner"])
        self.assertEqual(team_data["claim_status"], "CLAIMED")
        self.assertIn("unread_count", team_data)

    def test_deletes_team_only_when_no_other_participant_is_claimed(self):
        delete_response = self.client.delete(
            f"/api/teams/{self.team.code}/",
            {"confirmation_code": self.team.code},
            format="json",
        )

        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Team.objects.filter(pk=self.team.pk).exists())

    def test_rejects_team_deletion_after_another_participant_claims(self):
        minji = Participant.objects.get(team=self.team, display_name="민지")
        member = User.objects.create(username="delete-member", kakao_id=902, kakao_nickname="민지")
        minji.claimed_by = member
        minji.save(update_fields=["claimed_by"])
        response = self.client.delete(
            f"/api/teams/{self.team.code}/",
            {"confirmation_code": self.team.code},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())

    def test_admin_updates_planned_end_and_participant_receives_countdown(self):
        response = self.client.patch(
            f"/api/teams/{self.team.code}/admin/planned-end/",
            {
                "planned_end_date": (timezone.localdate() + timedelta(days=3)).isoformat(),
                "planned_end_timezone": "Asia/Seoul",
            },
            format="json",
        )
        countdown_response = self.client.get(f"/api/teams/{self.team.code}/countdown/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["planned_end_timezone"], "Asia/Seoul")
        self.assertEqual(countdown_response.status_code, 200)
        self.assertEqual(countdown_response.data["team_code"], self.team.code)
        self.assertTrue(countdown_response.data["remaining"].startswith("D-"))
        self.assertGreater(countdown_response.data["remaining_days"], 0)

        self.client.patch(
            f"/api/teams/{self.team.code}/admin/planned-end/",
            {
                "planned_end_date": timezone.localdate().isoformat(),
                "planned_end_timezone": "Asia/Seoul",
            },
            format="json",
        )
        d_day_response = self.client.get(f"/api/teams/{self.team.code}/countdown/")

        self.assertEqual(d_day_response.status_code, 200)
        self.assertEqual(d_day_response.data["remaining"], "D-Day!")

    def test_admin_can_change_reveal_mode_only_while_active(self):
        update_response = self.client.patch(
            f"/api/teams/{self.team.code}/admin/reveal-mode/",
            {"reveal_mode": Team.RevealMode.ADMIN},
            format="json",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data["reveal_mode"], Team.RevealMode.ADMIN)
        self.assertEqual(update_response.data["reveal_status"], Team.RevealStatus.MANUAL_PENDING)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                f"/api/teams/{self.team.code}/admin/end/",
                {"confirmation_code": self.team.code},
                format="json",
            )
        ended_update_response = self.client.patch(
            f"/api/teams/{self.team.code}/admin/reveal-mode/",
            {"reveal_mode": Team.RevealMode.AUTO},
            format="json",
        )

        self.assertEqual(ended_update_response.status_code, 400)

    def test_admin_can_update_rules_only_while_active(self):
        update_response = self.client.patch(
            f"/api/teams/{self.team.code}/admin/rules/",
            {"rules": "1) 익명 지키기\n2) 즐겁게 참여하기"},
            format="json",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data["rules"], "1) 익명 지키기\n2) 즐겁게 참여하기")

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                f"/api/teams/{self.team.code}/admin/end/",
                {"confirmation_code": self.team.code},
                format="json",
            )
        ended_update_response = self.client.patch(
            f"/api/teams/{self.team.code}/admin/rules/",
            {"rules": "수정할 수 없는 규칙"},
            format="json",
        )

        self.assertEqual(ended_update_response.status_code, 400)

    def test_admin_can_send_announcement_to_claimed_members(self):
        minji = Participant.objects.get(team=self.team, display_name="민지")
        member = User.objects.create(username="announcement-member", kakao_id=903, kakao_nickname="민지")
        minji.claimed_by = member
        minji.save(update_fields=["claimed_by"])

        response = self.client.post(
            f"/api/teams/{self.team.code}/admin/announcement/",
            {"message": "오늘도 마니또를 챙겨 주세요!"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["sent_count"], 1)
        notification = member.notifications.get()
        self.assertEqual(notification.kind, "TEAM_ANNOUNCEMENT")
        self.assertEqual(notification.body, "오늘도 마니또를 챙겨 주세요!")

    def test_end_requires_exact_code_retains_messages_and_allows_result(self):
        owner_participant = Participant.objects.get(team=self.team, display_name="관리자")
        message = Message.objects.create(
            team=self.team,
            sender=owner_participant,
            recipient=owner_participant.assigned_to,
            content="종료 전에 보낸 메시지",
        )
        wrong_response = self.client.post(
            f"/api/teams/{self.team.code}/admin/end/",
            {"confirmation_code": "wrong-code"},
            format="json",
        )
        end_response = self.client.post(
            f"/api/teams/{self.team.code}/admin/end/",
            {"confirmation_code": self.team.code},
            format="json",
        )
        result_response = self.client.get(f"/api/teams/{self.team.code}/result/")

        self.assertEqual(wrong_response.status_code, 400)
        self.assertEqual(end_response.status_code, 200)
        self.assertEqual(result_response.status_code, 200)
        self.assertTrue(Message.objects.filter(pk=message.pk).exists())

    def test_admin_reveal_mode_hides_participant_results_and_shows_admin_mapping(self):
        self.team.reveal_mode = Team.RevealMode.ADMIN
        self.team.reveal_status = Team.RevealStatus.MANUAL_PENDING
        self.team.save(update_fields=["reveal_mode", "reveal_status"])
        with self.captureOnCommitCallbacks(execute=True):
            end_response = self.client.post(
                f"/api/teams/{self.team.code}/admin/end/",
                {"confirmation_code": self.team.code},
                format="json",
            )
        result_response = self.client.get(f"/api/teams/{self.team.code}/result/")
        dashboard_response = self.client.get(
            f"/api/teams/{self.team.code}/admin/dashboard/",
        )
        release_response = self.client.post(
            f"/api/teams/{self.team.code}/admin/release-results/",
            {},
            format="json",
        )
        released_result_response = self.client.get(f"/api/teams/{self.team.code}/result/")

        self.assertEqual(end_response.status_code, 200)
        self.assertEqual(end_response.data["reveal_mode"], Team.RevealMode.ADMIN)
        self.assertEqual(result_response.status_code, 403)
        self.assertEqual(result_response.data["reveal_mode"], Team.RevealMode.ADMIN)
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(len(dashboard_response.data["reveal_assignments"]), 3)
        self.assertEqual(release_response.status_code, 200)
        self.assertEqual(release_response.data["reveal_status"], Team.RevealStatus.MANUAL_RELEASED)
        self.assertEqual(released_result_response.status_code, 200)

    def test_rejects_non_owner_from_admin_dashboard(self):
        outsider = User.objects.create(username="not_owner", kakao_id=903, kakao_nickname="외부인")
        client = APIClient()
        client.force_authenticate(outsider)

        response = client.get(f"/api/teams/{self.team.code}/admin/dashboard/")

        self.assertEqual(response.status_code, 403)
