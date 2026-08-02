from datetime import datetime, time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.models import Notification
from apps.teams.models import Participant, ScoreEvent, Team
from apps.teams.leaderboard_services import generate_leaderboard_snapshot

from .models import QuizItem, QuizRound, SystemQuizQuestion, TeamQuizSettings
from .seed_parser import parse_quiz_markdown, write_seed_json
from .services import (
    QuizError,
    confirm_evaluation,
    confirm_reference_answer,
    create_due_round,
    has_pending_reference_answer,
    has_pending_solve_reminder,
    participant_quiz_rate,
    process_round,
    remind_pending_quiz_participants,
    save_solution_draft,
    update_quiz_settings,
)


class QuizSeedParserTests(TestCase):
    def test_tracked_seed_load_is_idempotent_and_contains_50_utf8_questions(self):
        call_command("seed_quiz_questions", verbosity=0)
        call_command("seed_quiz_questions", verbosity=0)
        self.assertEqual(SystemQuizQuestion.objects.count(), 50)
        self.assertEqual(SystemQuizQuestion.objects.first().stable_id, "SYSTEM_001")
        self.assertEqual(SystemQuizQuestion.objects.last().stable_id, "SYSTEM_050")
        self.assertFalse(SystemQuizQuestion.objects.filter(body__contains="\ufffd").exists())

    def test_parses_uncategorized_questions_without_changing_text(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "questions.md"
            output = Path(directory) / "questions.json"
            source.write_text("1. 첫 질문  \n2. 두 번째 질문\n", encoding="utf-8")
            questions = parse_quiz_markdown(source)
            write_seed_json(questions, output)

            self.assertEqual([question["stable_id"] for question in questions], ["SYSTEM_001", "SYSTEM_002"])
            self.assertEqual(questions[0]["category"], "미분류")
            self.assertEqual(questions[0]["body"], "첫 질문  ")
            self.assertIn("첫 질문", output.read_text(encoding="utf-8"))

    def test_rejects_non_consecutive_numbers_and_replacement_character(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "questions.md"
            source.write_text("1. 첫 질문\n3. 세 번째 질문\n", encoding="utf-8")
            with self.assertRaisesMessage(ValueError, "연속"):
                parse_quiz_markdown(source)
            source.write_text("1. 잘못된 \ufffd 질문\n", encoding="utf-8")
            with self.assertRaisesMessage(ValueError, "대체문자"):
                parse_quiz_markdown(source)


@override_settings(QUIZ_SCORE_MULTIPLIER=3)
class QuizFlowTests(TestCase):
    def setUp(self):
        self.users = [
            User.objects.create(username=f"user-{index}", kakao_id=100 + index, kakao_nickname=f"참가자{index}")
            for index in range(3)
        ]
        self.team = Team.objects.create(
            code="quiz-team",
            owner=self.users[0],
            status=Team.Status.ACTIVE,
        )
        self.participants = [
            Participant.objects.create(
                team=self.team,
                display_name=f"참가자{index}",
                claimed_by=user,
                leaderboard_score=10,
            )
            for index, user in enumerate(self.users)
        ]
        for index, participant in enumerate(self.participants):
            participant.assigned_to = self.participants[(index + 1) % len(self.participants)]
            participant.save(update_fields=["assigned_to"])
        for index in range(1, 5):
            SystemQuizQuestion.objects.create(
                stable_id=f"SYSTEM_{index:03d}",
                original_number=index,
                category="테스트",
                body=f"질문 {index}",
                display_order=index,
            )
        self.now = timezone.now()
        self.settings = TeamQuizSettings.objects.create(
            team=self.team,
            enabled=True,
            quiz_timezone="Asia/Seoul",
            reference_days=1,
            solve_days=1,
            next_round_starts_at=self.now,
        )

    def create_round(self):
        return create_due_round(self.team.id, self.now)

    def test_creates_one_fixed_item_per_relationship_and_notifications(self):
        round_obj = self.create_round()
        duplicate = create_due_round(self.team.id, self.now)

        self.assertEqual(round_obj.items.count(), 3)
        self.assertIsNone(duplicate)
        self.assertEqual(QuizRound.objects.filter(team=self.team).count(), 1)
        self.assertEqual(
            {item.solver.assigned_to_id for item in round_obj.items.select_related("solver")},
            {item.author_id for item in round_obj.items.all()},
        )
        self.assertEqual(
            Notification.objects.filter(kind=Notification.Kind.QUIZ_REFERENCE_OPEN).count(),
            3,
        )
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.next_round_starts_at, round_obj.solve_ends_at)

    def test_reference_is_immutable_and_blank_solution_keeps_last_valid_draft(self):
        round_obj = self.create_round()
        item = round_obj.items.get(author=self.participants[0])
        confirm_reference_answer(self.team, item.id, self.users[0], "정답", self.now)
        same = confirm_reference_answer(self.team, item.id, self.users[0], "정답", self.now)
        self.assertEqual(same.reference_answer, "정답")
        with self.assertRaises(QuizError):
            confirm_reference_answer(self.team, item.id, self.users[0], "다른 답", self.now)

        solve_time = round_obj.reference_ends_at + timedelta(minutes=1)
        save_solution_draft(self.team, item.id, item.solver.claimed_by, "유효한 풀이", solve_time)
        saved = save_solution_draft(self.team, item.id, item.solver.claimed_by, "   ", solve_time)
        self.assertEqual(saved.solution_draft, "유효한 풀이")

    def test_pending_reference_attention_is_independent_from_notification_read(self):
        self.create_round()
        Notification.objects.filter(recipient=self.users[0]).update(is_read=True)
        self.assertTrue(has_pending_reference_answer(self.users[0], self.now))

    def test_unsaved_solution_gets_one_24_hour_reminder_and_attention(self):
        round_obj = self.create_round()
        round_obj.solve_ends_at = round_obj.reference_ends_at + timedelta(days=2)
        round_obj.evaluation_ends_at = round_obj.solve_ends_at + timedelta(days=round_obj.reference_days)
        round_obj.save(update_fields=["solve_ends_at", "evaluation_ends_at"])
        item = round_obj.items.get(solver=self.participants[0])
        item.reference_answer = "기준"
        item.reference_confirmed_at = self.now
        item.save(update_fields=["reference_answer", "reference_confirmed_at"])

        reminder_at = round_obj.solve_ends_at - timedelta(hours=24)
        process_round(round_obj.id, reminder_at - timedelta(seconds=1))
        self.assertFalse(has_pending_solve_reminder(self.users[0], reminder_at - timedelta(seconds=1)))

        process_round(round_obj.id, reminder_at)
        item.refresh_from_db()
        reminder = Notification.objects.get(
            dedupe_key=f"quiz:{round_obj.id}:solve:reminder-24h:{self.users[0].id}"
        )
        self.assertEqual(reminder.kind, Notification.Kind.QUIZ_SOLVE_OPEN)
        self.assertIsNotNone(item.solve_reminder_sent_at)
        self.assertTrue(has_pending_solve_reminder(self.users[0], reminder_at))
        reminder.is_read = True
        reminder.save(update_fields=["is_read"])
        self.assertTrue(has_pending_solve_reminder(self.users[0], reminder_at))
        self.assertNotIn(item.question_snapshot, f"{reminder.title}{reminder.body}{reminder.data}")

        process_round(round_obj.id, reminder_at + timedelta(minutes=1))
        self.assertEqual(
            Notification.objects.filter(
                dedupe_key=f"quiz:{round_obj.id}:solve:reminder-24h:{self.users[0].id}"
            ).count(),
            1,
        )

        client = APIClient()
        client.force_authenticate(self.users[0])
        with patch("apps.quizzes.services.timezone.now", return_value=reminder_at):
            response = client.get("/api/notifications/")
        self.assertTrue(response.data["has_pending_quiz_solve_reminder"])

        save_solution_draft(
            self.team,
            item.id,
            self.users[0],
            "저장된 풀이",
            reminder_at + timedelta(minutes=2),
        )
        self.assertFalse(
            has_pending_solve_reminder(self.users[0], reminder_at + timedelta(minutes=2))
        )

    def test_all_four_settlement_paths_and_rate(self):
        round_obj = self.create_round()
        items = list(round_obj.items.order_by("id"))
        items[1].reference_answer = "기준"
        items[1].reference_confirmed_at = self.now
        items[1].save(update_fields=["reference_answer", "reference_confirmed_at"])
        items[2].reference_answer = "기준"
        items[2].reference_confirmed_at = self.now
        items[2].solution_draft = "풀이"
        items[2].solution_draft_saved_at = self.now
        items[2].save(
            update_fields=[
                "reference_answer",
                "reference_confirmed_at",
                "solution_draft",
                "solution_draft_saved_at",
            ]
        )

        process_round(round_obj.id, round_obj.solve_ends_at + timedelta(minutes=1))
        items[0].refresh_from_db()
        items[1].refresh_from_db()
        items[2].refresh_from_db()
        self.assertEqual(items[0].settlement_kind, QuizItem.SettlementKind.REFERENCE_MISSING)
        self.assertEqual(items[1].settlement_kind, QuizItem.SettlementKind.SOLUTION_MISSING)
        self.assertIsNotNone(items[2].solution_submitted_at)

        evaluator = items[2].author.claimed_by
        confirm_evaluation(
            self.team,
            items[2].id,
            evaluator,
            2,
            round_obj.solve_ends_at + timedelta(minutes=2),
        )
        confirm_evaluation(
            self.team,
            items[2].id,
            evaluator,
            5,
            round_obj.solve_ends_at + timedelta(minutes=3),
        )
        items[2].refresh_from_db()
        self.assertEqual(items[2].evaluation_score, 5)
        self.assertFalse(items[2].settled_at)
        self.assertIsNone(participant_quiz_rate(items[2].solver))
        client = APIClient()
        client.force_authenticate(evaluator)
        with patch(
            "apps.quizzes.services.timezone.now",
            return_value=round_obj.solve_ends_at + timedelta(minutes=4),
        ):
            response = client.get(f"/api/teams/{self.team.code}/quiz/")
        self.assertEqual(response.data["evaluation_task"]["score"], 5)

        process_round(round_obj.id, round_obj.evaluation_ends_at + timedelta(minutes=1))
        items[2].refresh_from_db()
        self.assertEqual(items[2].settlement_kind, QuizItem.SettlementKind.EVALUATED)
        self.assertEqual(participant_quiz_rate(items[2].solver), 100.0)

        next_sequence = (
            QuizRound.objects.filter(team=self.team)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
            + 1
        )
        second_round = QuizRound.objects.create(
            team=self.team,
            sequence=next_sequence,
            question_mode=QuizRound.QuestionMode.SYSTEM,
            quiz_timezone="Asia/Seoul",
            reference_days=1,
            solve_days=1,
            starts_at=self.now - timedelta(days=3),
            reference_ends_at=self.now - timedelta(days=2),
            solve_ends_at=self.now - timedelta(days=1),
            evaluation_ends_at=self.now,
        )
        missing_eval = QuizItem.objects.create(
            round=second_round,
            author=self.participants[0],
            solver=self.participants[2],
            system_question=SystemQuizQuestion.objects.first(),
            question_kind=QuizItem.QuestionKind.SYSTEM,
            question_key="SYSTEM_001",
            question_normalized="질문 1",
            question_snapshot="질문 1",
            reference_answer="기준",
            reference_confirmed_at=second_round.reference_ends_at - timedelta(minutes=1),
            solution_draft="풀이",
            solution_draft_saved_at=second_round.solve_ends_at - timedelta(minutes=1),
        )
        process_round(second_round.id, self.now + timedelta(minutes=1))
        missing_eval.refresh_from_db()
        self.assertEqual(missing_eval.settlement_kind, QuizItem.SettlementKind.EVALUATION_MISSING)
        self.assertEqual(missing_eval.raw_score, 2)

    def test_penalty_clamps_at_zero_and_records_requested_and_actual_points(self):
        round_obj = self.create_round()
        item = round_obj.items.first()
        item.author.leaderboard_score = 2
        item.author.save(update_fields=["leaderboard_score"])
        item.reference_answer = "기준"
        item.reference_confirmed_at = self.now
        item.solution_draft = "풀이"
        item.solution_draft_saved_at = self.now
        item.save(
            update_fields=[
                "reference_answer",
                "reference_confirmed_at",
                "solution_draft",
                "solution_draft_saved_at",
            ]
        )
        QuizItem.objects.filter(round=round_obj).exclude(pk=item.pk).update(
            settlement_kind=QuizItem.SettlementKind.REFERENCE_MISSING,
            raw_score=3,
            rate_max_score=0,
            settled_at=self.now,
        )
        process_round(round_obj.id, round_obj.evaluation_ends_at + timedelta(minutes=1))

        event = ScoreEvent.objects.get(
            quiz_item=item,
            event_type=ScoreEvent.Type.QUIZ_AUTHOR_ADJUSTMENT,
        )
        item.author.refresh_from_db()
        self.assertEqual(event.requested_points, -6)
        self.assertEqual(event.points, -2)
        self.assertEqual(item.author.leaderboard_score, 0)
        process_round(round_obj.id, round_obj.evaluation_ends_at + timedelta(minutes=2))
        self.assertEqual(
            ScoreEvent.objects.filter(quiz_item=item, event_type=event.event_type).count(),
            1,
        )

    def test_api_never_exposes_solver_identity_to_evaluator(self):
        round_obj = self.create_round()
        item = round_obj.items.get(author=self.participants[0])
        item.reference_answer = "기준"
        item.reference_confirmed_at = self.now
        item.solution_draft = "풀이"
        item.solution_submitted = "풀이"
        item.solution_submitted_at = round_obj.solve_ends_at
        item.save(
            update_fields=[
                "reference_answer",
                "reference_confirmed_at",
                "solution_draft",
                "solution_submitted",
                "solution_submitted_at",
            ]
        )
        client = APIClient()
        client.force_authenticate(self.users[0])
        evaluation_time = round_obj.solve_ends_at + timedelta(minutes=1)
        with patch("apps.quizzes.services.timezone.now", return_value=evaluation_time):
            response = client.get(f"/api/teams/{self.team.code}/quiz/")
        payload = response.json()["evaluation_task"]
        serialized = str(payload).lower()
        self.assertNotIn("solver", serialized)
        self.assertNotIn("participant", serialized)
        self.assertNotIn("user_id", serialized)

    def test_admin_quiz_api_exposes_only_aggregate_progress(self):
        round_obj = self.create_round()
        completed_item = round_obj.items.get(author=self.participants[0])
        completed_item.reference_answer = "기준"
        completed_item.reference_confirmed_at = self.now + timedelta(minutes=1)
        completed_item.save(update_fields=["reference_answer", "reference_confirmed_at"])

        client = APIClient()
        client.force_authenticate(self.team.owner)
        with patch("apps.quizzes.services.timezone.now", return_value=self.now + timedelta(minutes=2)):
            response = client.get(f"/api/teams/{self.team.code}/admin/quiz/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("participants", response.data)
        self.assertEqual(len(response.data["rounds"]), 1)
        round_payload = response.data["rounds"][0]
        self.assertEqual(round_payload["progress"]["reference"], {"completed": 1, "total": 3})
        self.assertEqual(round_payload["pending_count"], 2)
        self.assertTrue(round_payload["can_remind"])
        serialized = str(response.data).lower()
        for participant in self.participants:
            self.assertNotIn(participant.display_name.lower(), serialized)
        self.assertNotIn("display_name", serialized)
        self.assertNotIn("participant_id", serialized)
        self.assertNotIn("user_id", serialized)

    def test_admin_quiz_api_limits_progress_to_two_latest_active_rounds(self):
        first_round = self.create_round()
        first_round.collision_decision = QuizRound.CollisionDecision.PENDING
        first_round.save(update_fields=["collision_decision"])
        for sequence in (2, 3):
            starts_at = self.now + timedelta(minutes=sequence)
            QuizRound.objects.create(
                team=self.team,
                sequence=sequence,
                question_mode=QuizRound.QuestionMode.SYSTEM,
                quiz_timezone="Asia/Seoul",
                reference_days=1,
                solve_days=1,
                starts_at=starts_at,
                reference_ends_at=starts_at + timedelta(days=1),
                solve_ends_at=starts_at + timedelta(days=2),
                evaluation_ends_at=starts_at + timedelta(days=3),
            )

        client = APIClient()
        client.force_authenticate(self.team.owner)
        with patch("apps.quizzes.services.timezone.now", return_value=self.now + timedelta(minutes=3)):
            response = client.get(f"/api/teams/{self.team.code}/admin/quiz/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [round_payload["sequence"] for round_payload in response.data["rounds"]],
            [3, 2],
        )
        self.assertEqual(response.data["pending_decision"]["round_id"], first_round.id)

    def test_admin_can_remind_pending_users_without_receiving_their_identities(self):
        round_obj = self.create_round()
        completed_item = round_obj.items.get(author=self.participants[0])
        completed_item.reference_answer = "기준"
        completed_item.reference_confirmed_at = self.now + timedelta(minutes=1)
        completed_item.save(update_fields=["reference_answer", "reference_confirmed_at"])

        client = APIClient()
        client.force_authenticate(self.team.owner)
        reminder_time = self.now + timedelta(minutes=2)
        with patch("apps.quizzes.services.timezone.now", return_value=reminder_time):
            response = client.post(
                f"/api/teams/{self.team.code}/admin/quiz/rounds/{round_obj.id}/remind-pending/"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"round_id": round_obj.id, "phase": "REFERENCE", "reminded_count": 2},
        )
        manual_notifications = Notification.objects.filter(
            dedupe_key__startswith=f"quiz:{round_obj.id}:reference:manual:"
        )
        self.assertEqual(manual_notifications.count(), 2)
        self.assertSetEqual(
            set(manual_notifications.values_list("recipient_id", flat=True)),
            {self.users[1].id, self.users[2].id},
        )
        for notification in manual_notifications:
            self.assertEqual(notification.data, {"quiz_round_id": round_obj.id})
            serialized = str(
                {
                    "title": notification.title,
                    "body": notification.body,
                    "data": notification.data,
                }
            ).lower()
            for participant in self.participants:
                self.assertNotIn(participant.display_name.lower(), serialized)

        pending_item = round_obj.items.get(author=self.participants[1])
        confirm_reference_answer(
            self.team,
            pending_item.id,
            self.users[1],
            "두 번째 기준",
            reminder_time + timedelta(minutes=1),
        )
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.users[1],
                dedupe_key__startswith=f"quiz:{round_obj.id}:reference:",
                is_read=False,
            ).exists()
        )

        client.force_authenticate(self.users[1])
        forbidden = client.post(
            f"/api/teams/{self.team.code}/admin/quiz/rounds/{round_obj.id}/remind-pending/"
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_manual_reminder_uses_current_solve_and_evaluation_tasks(self):
        round_obj = self.create_round()
        for item in round_obj.items.all():
            item.reference_answer = "기준"
            item.reference_confirmed_at = self.now + timedelta(minutes=1)
            item.save(update_fields=["reference_answer", "reference_confirmed_at"])

        solve_time = round_obj.reference_ends_at + timedelta(minutes=1)
        saved_item = round_obj.items.get(solver=self.participants[0])
        save_solution_draft(
            self.team,
            saved_item.id,
            self.users[0],
            "저장된 풀이",
            solve_time,
        )
        solve_result = remind_pending_quiz_participants(
            self.team,
            round_obj.id,
            solve_time + timedelta(minutes=1),
        )
        self.assertEqual(solve_result["phase"], "SOLVE")
        self.assertEqual(solve_result["reminded_count"], 2)
        self.assertSetEqual(
            set(
                Notification.objects.filter(
                    dedupe_key__startswith=f"quiz:{round_obj.id}:solve:manual:"
                ).values_list("recipient_id", flat=True)
            ),
            {self.users[1].id, self.users[2].id},
        )

        round_obj.items.filter(solution_draft_saved_at__isnull=True).update(
            solution_draft="나머지 풀이",
            solution_draft_saved_at=solve_time,
        )
        process_round(round_obj.id, round_obj.solve_ends_at)
        evaluated_item = round_obj.items.get(author=self.participants[0])
        evaluated_item.evaluation_score = 4
        evaluated_item.evaluated_at = round_obj.solve_ends_at + timedelta(minutes=1)
        evaluated_item.save(update_fields=["evaluation_score", "evaluated_at"])

        evaluation_result = remind_pending_quiz_participants(
            self.team,
            round_obj.id,
            round_obj.solve_ends_at + timedelta(minutes=2),
        )
        self.assertEqual(evaluation_result["phase"], "EVALUATION")
        self.assertEqual(evaluation_result["reminded_count"], 2)
        self.assertSetEqual(
            set(
                Notification.objects.filter(
                    dedupe_key__startswith=f"quiz:{round_obj.id}:evaluation:manual:"
                ).values_list("recipient_id", flat=True)
            ),
            {self.users[1].id, self.users[2].id},
        )

    def test_enabling_requires_all_claims_and_schedules_next_local_midnight(self):
        self.settings.enabled = False
        self.settings.next_round_starts_at = None
        self.settings.save(update_fields=["enabled", "next_round_starts_at"])
        self.participants[-1].claimed_by = None
        self.participants[-1].save(update_fields=["claimed_by"])
        with self.assertRaises(QuizError):
            update_quiz_settings(
                self.team,
                {"enabled": True, "quiz_timezone": "Asia/Seoul"},
                self.now,
            )

    def test_collision_at_solve_start_waits_then_auto_cancels_without_score(self):
        zone = ZoneInfo("Asia/Seoul")
        local_date = timezone.localtime(self.now, zone).date() + timedelta(days=1)
        starts_at = datetime.combine(local_date, time.min, tzinfo=zone)
        self.settings.next_round_starts_at = starts_at
        self.settings.save(update_fields=["next_round_starts_at"])
        self.team.planned_end_date = local_date + timedelta(days=1)
        self.team.save(update_fields=["planned_end_date"])
        round_obj = create_due_round(self.team.id, starts_at)
        self.assertEqual(round_obj.collision_decision, QuizRound.CollisionDecision.PENDING)

        process_round(round_obj.id, round_obj.reference_ends_at)
        round_obj.refresh_from_db()
        self.settings.refresh_from_db()
        self.assertEqual(round_obj.status, QuizRound.Status.CANCELLED)
        self.assertFalse(self.settings.enabled)
        self.assertFalse(ScoreEvent.objects.filter(quiz_item__round=round_obj).exists())

    def test_quiz_rate_is_exposed_only_after_results_release(self):
        round_obj = self.create_round()
        item = round_obj.items.get(solver=self.participants[0])
        item.settlement_kind = QuizItem.SettlementKind.EVALUATED
        item.raw_score = 4
        item.rate_max_score = 5
        item.settled_at = self.now
        item.save(update_fields=["settlement_kind", "raw_score", "rate_max_score", "settled_at"])
        generate_leaderboard_snapshot(self.team)
        client = APIClient()
        client.force_authenticate(self.users[0])

        active = client.get(f"/api/teams/{self.team.code}/leaderboard/")
        self.assertNotIn("quiz_score_rate", str(active.data))
        self.team.status = Team.Status.ENDED
        self.team.ended_at = self.now
        self.team.reveal_status = Team.RevealStatus.AUTO_RELEASED
        self.team.save(update_fields=["status", "ended_at", "reveal_status"])
        released = client.get(f"/api/teams/{self.team.code}/leaderboard/")
        my_entry = next(entry for entry in released.data["entries"] if entry["is_me"])
        self.assertEqual(my_entry["quiz_score_rate"], 80.0)
