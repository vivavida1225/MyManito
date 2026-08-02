from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.accounts.models import User
from apps.teams.leaderboard_services import award_service_access_scores
from apps.teams.models import Participant, ScoreEvent, Team

from .models import Message
from .services import create_message, get_chat_room_for_user, make_room_id


@skipUnless(connection.vendor == "postgresql", "PostgreSQL 동시 쓰기 검증입니다.")
class PostgreSQLConcurrentWriteTests(TransactionTestCase):
    reset_sequences = True

    def create_room(self, suffix):
        first_user = User.objects.create(
            username=f"postgres-first-{suffix}",
            kakao_id=10000 + suffix * 10,
        )
        second_user = User.objects.create(
            username=f"postgres-second-{suffix}",
            kakao_id=10001 + suffix * 10,
        )
        team = Team.objects.create(
            code=f"postgres-team-{suffix}",
            owner=first_user,
            status=Team.Status.ACTIVE,
        )
        first = Participant.objects.create(
            team=team,
            display_name=f"첫 번째-{suffix}",
            claimed_by=first_user,
        )
        second = Participant.objects.create(
            team=team,
            display_name=f"두 번째-{suffix}",
            claimed_by=second_user,
        )
        first.assigned_to = second
        second.assigned_to = first
        first.save(update_fields=["assigned_to"])
        second.save(update_fields=["assigned_to"])
        return {
            "team_id": team.id,
            "room_id": make_room_id(first.id, second.id),
            "first_user_id": first_user.id,
            "second_user_id": second_user.id,
        }

    def run_concurrently(self, *operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                operation()
                return None
            except Exception as error:
                return error
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            errors = list(executor.map(run, operations))
        self.assertEqual(
            [f"{type(error).__name__}: {error}" for error in errors if error],
            [],
        )

    @staticmethod
    def send_message(room_id, user_id, content):
        user = User.objects.get(pk=user_id)
        room = get_chat_room_for_user(room_id=room_id, user=user)
        create_message(room=room, content=content, image=None)

    @patch("apps.chat.services.notify_message_recipient_async")
    def test_different_teams_can_write_messages_concurrently(self, _notify_mock):
        first_room = self.create_room(1)
        second_room = self.create_room(2)

        self.run_concurrently(
            lambda: self.send_message(
                first_room["room_id"],
                first_room["first_user_id"],
                "첫 번째 팀 메시지",
            ),
            lambda: self.send_message(
                second_room["room_id"],
                second_room["first_user_id"],
                "두 번째 팀 메시지",
            ),
        )

        self.assertEqual(
            Message.objects.filter(
                content__in=["첫 번째 팀 메시지", "두 번째 팀 메시지"]
            ).count(),
            2,
        )

    @patch("apps.chat.services.notify_message_recipient_async")
    def test_same_team_messages_are_serialized_without_failure(self, _notify_mock):
        room = self.create_room(3)

        self.run_concurrently(
            lambda: self.send_message(
                room["room_id"],
                room["first_user_id"],
                "서로 마주보는 첫 메시지",
            ),
            lambda: self.send_message(
                room["room_id"],
                room["second_user_id"],
                "서로 마주보는 두 번째 메시지",
            ),
        )

        self.assertEqual(Message.objects.filter(team_id=room["team_id"]).count(), 2)

    @patch("apps.chat.services.notify_message_recipient_async")
    def test_chat_and_service_access_score_can_write_concurrently(self, _notify_mock):
        room = self.create_room(4)

        def access_service():
            user = User.objects.get(pk=room["second_user_id"])
            award_service_access_scores(user=user)

        self.run_concurrently(
            lambda: self.send_message(
                room["room_id"],
                room["first_user_id"],
                "점수와 동시에 보내는 메시지",
            ),
            access_service,
        )

        self.assertTrue(
            ScoreEvent.objects.filter(
                team_id=room["team_id"],
                event_type=ScoreEvent.Type.CHAT_MESSAGE,
            ).exists()
        )
        self.assertTrue(
            ScoreEvent.objects.filter(
                team_id=room["team_id"],
                event_type=ScoreEvent.Type.SERVICE_ACCESS,
            ).exists()
        )
