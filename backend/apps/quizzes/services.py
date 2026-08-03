import random
from datetime import datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.conf import settings as django_settings
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.push import send_web_push_async
from apps.chat.models import Notification
from apps.realtime.events import publish_user_events_on_commit
from apps.teams.models import Participant, ScoreEvent, Team

from .models import QuizItem, QuizRound, SystemQuizQuestion, TeamQuizSettings


class QuizError(Exception):
    pass


class QuizConflictConfirmationRequired(QuizError):
    def __init__(self, round_id):
        self.round_id = round_id
        super().__init__("풀이 중인 퀴즈 회차와 종료 예정일이 겹칩니다.")


def normalize_question(value):
    return " ".join((value or "").strip().split())


def next_local_rotation(now, timezone_name, rotation_hour):
    zone = ZoneInfo(timezone_name)
    local_now = timezone.localtime(now, zone)
    candidate = datetime.combine(
        local_now.date(),
        time(hour=rotation_hour),
        tzinfo=zone,
    )
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


def local_rotation_after_days(value, days, timezone_name, rotation_hour):
    zone = ZoneInfo(timezone_name)
    local_date = timezone.localtime(value, zone).date() + timedelta(days=days)
    return datetime.combine(local_date, time(hour=rotation_hour), tzinfo=zone)


def planned_end_in_quiz_timezone(team, timezone_name, planned_end_date=None):
    end_date = planned_end_date if planned_end_date is not None else team.planned_end_date
    if end_date is None:
        return None
    return datetime.combine(end_date, time.min, tzinfo=ZoneInfo(timezone_name))


def round_collides_with_end(team, round_obj, planned_end_date=None):
    end_at = planned_end_in_quiz_timezone(team, round_obj.quiz_timezone, planned_end_date)
    return bool(end_at and round_obj.reference_ends_at <= end_at < round_obj.solve_ends_at)


def preview_collision(team, quiz_settings, planned_end_date=None):
    if not quiz_settings.next_round_starts_at or not quiz_settings.quiz_timezone:
        return False
    reference_end = local_rotation_after_days(
        quiz_settings.next_round_starts_at,
        quiz_settings.reference_days,
        quiz_settings.quiz_timezone,
        quiz_settings.rotation_hour,
    )
    solve_end = local_rotation_after_days(
        quiz_settings.next_round_starts_at,
        quiz_settings.reference_days + quiz_settings.solve_days,
        quiz_settings.quiz_timezone,
        quiz_settings.rotation_hour,
    )
    end_at = planned_end_in_quiz_timezone(team, quiz_settings.quiz_timezone, planned_end_date)
    return bool(end_at and reference_end <= end_at < solve_end)


def _quiz_recipient_ids(team):
    recipient_ids = set(
        Participant.objects.filter(team=team, claimed_by__isnull=False).values_list("claimed_by_id", flat=True)
    )
    recipient_ids.add(team.owner_id)
    return sorted(recipient_ids)


def publish_quiz_changed(team):
    publish_user_events_on_commit(_quiz_recipient_ids(team), "quiz.changed", team_code=team.code)


def create_quiz_notification(*, recipient_id, team, kind, title, body, dedupe_key, path, round_id=None):
    notification, created = Notification.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "recipient_id": recipient_id,
            "team": team,
            "kind": kind,
            "title": title,
            "body": body,
            "data": {"quiz_round_id": round_id} if round_id else {},
        },
    )
    if not created:
        return notification, False
    transaction.on_commit(
        lambda: send_web_push_async(
            user_id=recipient_id,
            title=title,
            body=body,
            path=path,
        )
    )
    publish_user_events_on_commit([recipient_id], "notifications.changed")
    return notification, True


def _mark_notification_keys_read(keys):
    keys = [key for key in keys if key]
    if not keys:
        return
    notifications = Notification.objects.filter(dedupe_key__in=keys, is_read=False)
    recipient_ids = list(notifications.order_by().values_list("recipient_id", flat=True).distinct())
    if notifications.update(is_read=True, read_at=timezone.now()):
        publish_user_events_on_commit(recipient_ids, "notifications.changed")


def _mark_round_notifications_read(round_obj, action):
    notifications = Notification.objects.filter(
        dedupe_key__startswith=f"quiz:{round_obj.id}:{action}:",
        is_read=False,
    )
    recipient_ids = list(notifications.order_by().values_list("recipient_id", flat=True).distinct())
    if notifications.update(is_read=True, read_at=timezone.now()):
        publish_user_events_on_commit(recipient_ids, "notifications.changed")


def _mark_quiz_action_notifications_read(round_id, action, recipient_id):
    notifications = Notification.objects.filter(
        recipient_id=recipient_id,
        dedupe_key__startswith=f"quiz:{round_id}:{action}:",
        is_read=False,
    )
    if notifications.update(is_read=True, read_at=timezone.now()):
        publish_user_events_on_commit([recipient_id], "notifications.changed")


@transaction.atomic
def notify_all_claimed_if_ready(team):
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    total_count = Participant.objects.filter(team=locked_team).count()
    claimed_count = Participant.objects.filter(team=locked_team, claimed_by__isnull=False).count()
    if not total_count or total_count != claimed_count:
        return False
    quiz_settings, _ = TeamQuizSettings.objects.select_for_update().get_or_create(team=locked_team)
    if quiz_settings.all_claimed_notified_at:
        return False
    quiz_settings.all_claimed_notified_at = timezone.now()
    quiz_settings.save(update_fields=["all_claimed_notified_at", "updated_at"])
    create_quiz_notification(
        recipient_id=locked_team.owner_id,
        team=locked_team,
        kind=Notification.Kind.QUIZ_READY,
        title="비밀 퀴즈를 시작할 수 있어요",
        body="모든 참여자가 본인 확인을 마쳤습니다. 관리자 설정에서 퀴즈 모드를 켜 주세요.",
        dedupe_key=f"quiz:ready:{locked_team.id}:{locked_team.owner_id}",
        path=f"/teams/{locked_team.code}/admin/quiz",
    )
    return True


def _used_question_data(author):
    used = QuizItem.objects.filter(author=author)
    return (
        set(used.exclude(system_question_id=None).values_list("system_question__stable_id", flat=True)),
        set(used.values_list("question_normalized", flat=True)),
    )


@transaction.atomic
def create_due_round(team_id, now=None):
    now = now or timezone.now()
    team = Team.objects.select_for_update().get(pk=team_id)
    quiz_settings = TeamQuizSettings.objects.select_for_update().filter(team=team).first()
    if (
        not quiz_settings
        or not quiz_settings.enabled
        or not quiz_settings.next_round_starts_at
        or quiz_settings.next_round_starts_at > now
        or team.status != Team.Status.ACTIVE
    ):
        return None

    participants = list(
        Participant.objects.select_for_update()
        .filter(team=team)
        .order_by("id")
    )
    if not participants or any(not participant.claimed_by_id or not participant.assigned_to_id for participant in participants):
        quiz_settings.enabled = False
        quiz_settings.next_round_starts_at = None
        quiz_settings.save(update_fields=["enabled", "next_round_starts_at", "updated_at"])
        return None

    starts_at = quiz_settings.next_round_starts_at
    existing = QuizRound.objects.filter(team=team, starts_at=starts_at).first()
    if existing:
        return existing
    sequence = (QuizRound.objects.filter(team=team).order_by("-sequence").values_list("sequence", flat=True).first() or 0) + 1
    reference_ends_at = local_rotation_after_days(
        starts_at,
        quiz_settings.reference_days,
        quiz_settings.quiz_timezone,
        quiz_settings.rotation_hour,
    )
    solve_ends_at = local_rotation_after_days(
        starts_at,
        quiz_settings.reference_days + quiz_settings.solve_days,
        quiz_settings.quiz_timezone,
        quiz_settings.rotation_hour,
    )
    evaluation_ends_at = local_rotation_after_days(
        starts_at,
        (quiz_settings.reference_days * 2) + quiz_settings.solve_days,
        quiz_settings.quiz_timezone,
        quiz_settings.rotation_hour,
    )
    common_question = quiz_settings.next_common_question.strip()
    question_mode = QuizRound.QuestionMode.COMMON if common_question else QuizRound.QuestionMode.SYSTEM

    assignments = []
    system_questions = list(SystemQuizQuestion.objects.filter(is_active=True).order_by("display_order", "id"))
    solver_by_author = {participant.assigned_to_id: participant for participant in participants}
    for author in participants:
        solver = solver_by_author.get(author.id)
        if solver is None:
            raise QuizError("마니또 관계에서 풀이자를 찾을 수 없습니다.")
        used_ids, used_normalized = _used_question_data(author)
        if common_question:
            normalized = normalize_question(common_question)
            if normalized in used_normalized:
                raise QuizError("이미 배정된 공통 질문입니다.")
            assignments.append((author, solver, None, common_question, normalized))
            continue
        candidates = [
            question
            for question in system_questions
            if question.stable_id not in used_ids and normalize_question(question.body) not in used_normalized
        ]
        if not candidates:
            quiz_settings.enabled = False
            quiz_settings.next_round_starts_at = None
            quiz_settings.save(update_fields=["enabled", "next_round_starts_at", "updated_at"])
            create_quiz_notification(
                recipient_id=team.owner_id,
                team=team,
                kind=Notification.Kind.QUIZ_POOL_EXHAUSTED,
                title="비밀 퀴즈 질문을 모두 사용했어요",
                body="새 공통 질문을 등록한 뒤 퀴즈 모드를 다시 켜 주세요.",
                dedupe_key=f"quiz:pool-exhausted:{team.id}:{int(starts_at.timestamp())}",
                path=f"/teams/{team.code}/admin/quiz",
            )
            publish_quiz_changed(team)
            return None
        question = random.choice(candidates)
        assignments.append((author, solver, question, question.body, normalize_question(question.body)))

    round_obj = QuizRound.objects.create(
        team=team,
        sequence=sequence,
        question_mode=question_mode,
        common_question_snapshot=common_question,
        quiz_timezone=quiz_settings.quiz_timezone,
        reference_days=quiz_settings.reference_days,
        solve_days=quiz_settings.solve_days,
        starts_at=starts_at,
        reference_ends_at=reference_ends_at,
        solve_ends_at=solve_ends_at,
        evaluation_ends_at=evaluation_ends_at,
    )
    if round_collides_with_end(team, round_obj):
        round_obj.collision_decision = QuizRound.CollisionDecision.PENDING
        round_obj.save(update_fields=["collision_decision"])

    QuizItem.objects.bulk_create(
        [
            QuizItem(
                round=round_obj,
                author=author,
                solver=solver,
                system_question=question,
                question_kind=(QuizItem.QuestionKind.SYSTEM if question else QuizItem.QuestionKind.COMMON),
                question_key=question.stable_id if question else f"COMMON:{normalized}",
                question_normalized=normalized,
                question_snapshot=body,
            )
            for author, solver, question, body, normalized in assignments
        ]
    )
    quiz_settings.next_round_starts_at = solve_ends_at
    quiz_settings.next_common_question = ""
    quiz_settings.next_common_question_normalized = ""
    quiz_settings.save(
        update_fields=[
            "next_round_starts_at",
            "next_common_question",
            "next_common_question_normalized",
            "updated_at",
        ]
    )
    for author in participants:
        create_quiz_notification(
            recipient_id=author.claimed_by_id,
            team=team,
            kind=Notification.Kind.QUIZ_REFERENCE_OPEN,
            title="새 비밀 퀴즈가 시작됐어요",
            body="나에 관한 기준 답안을 입력하고 확정해 주세요.",
            dedupe_key=f"quiz:{round_obj.id}:reference:{author.claimed_by_id}",
            path=f"/teams/{team.code}/quiz",
            round_id=round_obj.id,
        )
    if round_obj.collision_decision == QuizRound.CollisionDecision.PENDING:
        create_quiz_notification(
            recipient_id=team.owner_id,
            team=team,
            kind=Notification.Kind.QUIZ_END_CONFLICT,
            title="퀴즈 일정과 종료 예정일이 겹쳐요",
            body="입력기간이 끝나기 전에 이번 회차의 진행 여부를 결정해 주세요.",
            dedupe_key=f"quiz:{round_obj.id}:collision:{team.owner_id}",
            path=f"/teams/{team.code}/admin/quiz",
            round_id=round_obj.id,
        )
    publish_quiz_changed(team)
    return round_obj


def _apply_quiz_score(item, participant_id, event_type, requested_points, reason):
    event = ScoreEvent.objects.filter(quiz_item=item, event_type=event_type).first()
    if event:
        return event.points
    participant = Participant.objects.select_for_update().get(pk=participant_id)
    actual_points = requested_points
    if requested_points < 0:
        actual_points = -min(participant.leaderboard_score, abs(requested_points))
    ScoreEvent.objects.create(
        team_id=item.round.team_id,
        participant=participant,
        event_type=event_type,
        quiz_item=item,
        points=actual_points,
        requested_points=requested_points,
        reason=reason,
    )
    participant.leaderboard_score += actual_points
    participant.save(update_fields=["leaderboard_score"])
    return actual_points


def _settle_item(item, settlement_kind, raw_score, rate_max_score):
    if item.settled_at:
        return
    multiplier = django_settings.QUIZ_SCORE_MULTIPLIER
    if settlement_kind == QuizItem.SettlementKind.REFERENCE_MISSING:
        _apply_quiz_score(
            item, item.solver_id, ScoreEvent.Type.QUIZ_SOLVER_RESULT, 3 * multiplier, settlement_kind
        )
    elif settlement_kind == QuizItem.SettlementKind.SOLUTION_MISSING:
        _apply_quiz_score(
            item, item.author_id, ScoreEvent.Type.QUIZ_AUTHOR_ADJUSTMENT, multiplier, settlement_kind
        )
    elif settlement_kind == QuizItem.SettlementKind.EVALUATED:
        _apply_quiz_score(
            item,
            item.solver_id,
            ScoreEvent.Type.QUIZ_SOLVER_RESULT,
            raw_score * multiplier,
            settlement_kind,
        )
        _apply_quiz_score(
            item, item.author_id, ScoreEvent.Type.QUIZ_AUTHOR_ADJUSTMENT, multiplier, settlement_kind
        )
    elif settlement_kind == QuizItem.SettlementKind.EVALUATION_MISSING:
        _apply_quiz_score(
            item, item.solver_id, ScoreEvent.Type.QUIZ_SOLVER_RESULT, 2 * multiplier, settlement_kind
        )
        _apply_quiz_score(
            item, item.author_id, ScoreEvent.Type.QUIZ_AUTHOR_ADJUSTMENT, -2 * multiplier, settlement_kind
        )
    item.settlement_kind = settlement_kind
    item.raw_score = raw_score
    item.rate_max_score = rate_max_score
    item.settled_at = timezone.now()
    item.save(update_fields=["settlement_kind", "raw_score", "rate_max_score", "settled_at"])


def _cancel_round(round_obj, reason, now):
    if round_obj.status == QuizRound.Status.CANCELLED:
        return
    round_obj.status = QuizRound.Status.CANCELLED
    round_obj.collision_decision = QuizRound.CollisionDecision.CANCEL
    round_obj.cancel_reason = reason
    round_obj.cancelled_at = now
    round_obj.save(
        update_fields=["status", "collision_decision", "cancel_reason", "cancelled_at"]
    )
    quiz_settings = TeamQuizSettings.objects.select_for_update().get(team=round_obj.team)
    quiz_settings.enabled = False
    quiz_settings.next_round_starts_at = None
    quiz_settings.save(update_fields=["enabled", "next_round_starts_at", "updated_at"])
    for recipient_id in Participant.objects.filter(
        team=round_obj.team, claimed_by__isnull=False
    ).values_list("claimed_by_id", flat=True):
        create_quiz_notification(
            recipient_id=recipient_id,
            team=round_obj.team,
            kind=Notification.Kind.QUIZ_ROUND_CANCELLED,
            title="이번 비밀 퀴즈 회차가 취소됐어요",
            body="취소된 회차에는 점수나 보상, 감점이 적용되지 않습니다.",
            dedupe_key=f"quiz:{round_obj.id}:cancelled:{recipient_id}",
            path=f"/teams/{round_obj.team.code}/quiz",
            round_id=round_obj.id,
        )
    _mark_round_notifications_read(round_obj, "reference")
    _mark_round_notifications_read(round_obj, "solve")
    _mark_round_notifications_read(round_obj, "evaluation")
    _mark_notification_keys_read([f"quiz:{round_obj.id}:collision:{round_obj.team.owner_id}"])
    publish_quiz_changed(round_obj.team)


@transaction.atomic
def process_round(round_id, now=None):
    now = now or timezone.now()
    team_id = QuizRound.objects.filter(pk=round_id).values_list("team_id", flat=True).first()
    if team_id is None:
        return None
    team = Team.objects.select_for_update().filter(pk=team_id).first()
    if team is None:
        return None
    round_obj = QuizRound.objects.select_for_update().filter(pk=round_id).first()
    if not round_obj or round_obj.status != QuizRound.Status.ACTIVE:
        return round_obj
    round_obj.team = team
    items = list(
        QuizItem.objects.select_for_update()
        .filter(round=round_obj)
        .select_related("author", "solver")
        .order_by("id")
    )
    changed = False

    if now >= round_obj.reference_ends_at and round_obj.collision_decision == QuizRound.CollisionDecision.PENDING:
        _cancel_round(round_obj, "END_CONFLICT_NO_DECISION", now)
        return round_obj

    if now >= round_obj.reference_ends_at and not round_obj.reference_processed_at:
        _mark_round_notifications_read(round_obj, "reference")
        for item in items:
            if not item.reference_confirmed_at or not item.solver.claimed_by_id:
                continue
            create_quiz_notification(
                recipient_id=item.solver.claimed_by_id,
                team=round_obj.team,
                kind=Notification.Kind.QUIZ_SOLVE_OPEN,
                title="풀 수 있는 비밀 퀴즈가 열렸어요",
                body="내가 챙겨주는 사람에 관한 답안을 임시 저장해 주세요.",
                dedupe_key=f"quiz:{round_obj.id}:solve:{item.solver.claimed_by_id}",
                path=f"/teams/{round_obj.team.code}/quiz",
                round_id=round_obj.id,
            )
        round_obj.reference_processed_at = now
        round_obj.save(update_fields=["reference_processed_at"])
        changed = True

    solve_reminder_at = round_obj.solve_ends_at - timedelta(hours=24)
    if (
        round_obj.reference_ends_at <= now < round_obj.solve_ends_at
        and now >= solve_reminder_at
        and round_obj.collision_decision != QuizRound.CollisionDecision.PENDING
    ):
        for item in items:
            if (
                item.solve_reminder_sent_at
                or not item.reference_confirmed_at
                or item.solution_draft_saved_at
                or not item.solver.claimed_by_id
            ):
                continue
            create_quiz_notification(
                recipient_id=item.solver.claimed_by_id,
                team=round_obj.team,
                kind=Notification.Kind.QUIZ_SOLVE_OPEN,
                title="비밀 퀴즈 풀이 마감이 하루 남았어요",
                body="아직 저장된 답안이 없습니다. 마감 전에 비밀 퀴즈를 풀어 주세요.",
                dedupe_key=f"quiz:{round_obj.id}:solve:reminder-24h:{item.solver.claimed_by_id}",
                path=f"/teams/{round_obj.team.code}/quiz",
                round_id=round_obj.id,
            )
            item.solve_reminder_sent_at = now
            item.save(update_fields=["solve_reminder_sent_at"])
            changed = True

    if now >= round_obj.solve_ends_at and not round_obj.solve_processed_at:
        _mark_round_notifications_read(round_obj, "solve")
        for item in items:
            if item.settled_at:
                continue
            if not item.reference_confirmed_at:
                _settle_item(item, QuizItem.SettlementKind.REFERENCE_MISSING, 3, 0)
                continue
            if not item.solution_draft.strip():
                _settle_item(item, QuizItem.SettlementKind.SOLUTION_MISSING, 0, 5)
                continue
            if not item.solution_submitted_at:
                item.solution_submitted = item.solution_draft
                item.solution_submitted_at = round_obj.solve_ends_at
                item.save(update_fields=["solution_submitted", "solution_submitted_at"])
            if item.author.claimed_by_id:
                create_quiz_notification(
                    recipient_id=item.author.claimed_by_id,
                    team=round_obj.team,
                    kind=Notification.Kind.QUIZ_EVALUATION_OPEN,
                    title="마니또의 답안을 평가해 주세요",
                    body="나를 챙기는 마니또가 제출한 답안을 1점부터 5점까지 평가해 주세요.",
                    dedupe_key=f"quiz:{round_obj.id}:evaluation:{item.author.claimed_by_id}",
                    path=f"/teams/{round_obj.team.code}/quiz",
                    round_id=round_obj.id,
                )
        round_obj.solve_processed_at = now
        round_obj.save(update_fields=["solve_processed_at"])
        changed = True

    if now >= round_obj.evaluation_ends_at and not round_obj.evaluation_processed_at:
        _mark_round_notifications_read(round_obj, "evaluation")
        for item in items:
            if not item.settled_at and item.solution_submitted_at:
                if item.evaluation_score is not None:
                    _settle_item(
                        item,
                        QuizItem.SettlementKind.EVALUATED,
                        item.evaluation_score,
                        5,
                    )
                else:
                    _settle_item(item, QuizItem.SettlementKind.EVALUATION_MISSING, 2, 5)
        round_obj.evaluation_processed_at = now
        round_obj.save(update_fields=["evaluation_processed_at"])
        changed = True

    if items and all(item.settled_at or QuizItem.objects.filter(pk=item.pk, settled_at__isnull=False).exists() for item in items):
        round_obj.status = QuizRound.Status.SETTLED
        round_obj.settled_at = now
        round_obj.save(update_fields=["status", "settled_at"])
        changed = True
    if changed:
        publish_quiz_changed(round_obj.team)
    return round_obj


def process_team_timeline(team_id, now=None, create_round=True):
    now = now or timezone.now()
    round_ids = list(
        QuizRound.objects.filter(team_id=team_id, status=QuizRound.Status.ACTIVE)
        .filter(
            Q(reference_ends_at__lte=now, reference_processed_at__isnull=True)
            | Q(
                reference_ends_at__lte=now,
                solve_ends_at__gt=now,
                solve_ends_at__lte=now + timedelta(hours=24),
                items__reference_confirmed_at__isnull=False,
                items__solution_draft_saved_at__isnull=True,
                items__solve_reminder_sent_at__isnull=True,
            )
            | Q(solve_ends_at__lte=now, solve_processed_at__isnull=True)
            | Q(evaluation_ends_at__lte=now, evaluation_processed_at__isnull=True)
        )
        .distinct()
        .values_list("id", flat=True)
    )
    for round_id in round_ids:
        process_round(round_id, now)
    if create_round:
        create_due_round(team_id, now)


def process_quiz_timeline(now=None):
    now = now or timezone.now()
    team_ids = set(
        QuizRound.objects.filter(status=QuizRound.Status.ACTIVE)
        .filter(
            Q(reference_ends_at__lte=now, reference_processed_at__isnull=True)
            | Q(
                reference_ends_at__lte=now,
                solve_ends_at__gt=now,
                solve_ends_at__lte=now + timedelta(hours=24),
                items__reference_confirmed_at__isnull=False,
                items__solution_draft_saved_at__isnull=True,
                items__solve_reminder_sent_at__isnull=True,
            )
            | Q(solve_ends_at__lte=now, solve_processed_at__isnull=True)
            | Q(evaluation_ends_at__lte=now, evaluation_processed_at__isnull=True)
        )
        .distinct()
        .values_list("team_id", flat=True)
    )
    team_ids.update(
        TeamQuizSettings.objects.filter(
            enabled=True,
            next_round_starts_at__isnull=False,
            next_round_starts_at__lte=now,
        ).values_list("team_id", flat=True)
    )
    for team_id in sorted(team_ids):
        process_team_timeline(team_id, now)
    return len(team_ids)


@transaction.atomic
def update_quiz_settings(team, validated_data, now=None):
    now = now or timezone.now()
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    if locked_team.status != Team.Status.ACTIVE:
        raise QuizError("진행 중인 팀의 퀴즈 설정만 변경할 수 있습니다.")
    quiz_settings, _ = TeamQuizSettings.objects.select_for_update().get_or_create(team=locked_team)
    reference_days = validated_data.get("reference_days", quiz_settings.reference_days)
    solve_days = validated_data.get("solve_days", quiz_settings.solve_days)
    if reference_days < 1 or solve_days < 1 or reference_days + solve_days > 7:
        raise QuizError("입력일수와 풀이일수는 각각 1일 이상이며 합계가 7일 이하여야 합니다.")

    rotation_hour = validated_data.get("rotation_hour", quiz_settings.rotation_hour)
    if rotation_hour < 0 or rotation_hour > 23:
        raise QuizError("기준 시간은 0시부터 23시 사이여야 합니다.")
    rotation_hour_changed = rotation_hour != quiz_settings.rotation_hour
    if rotation_hour_changed and QuizRound.objects.filter(
        team=locked_team,
        status=QuizRound.Status.ACTIVE,
    ).exists():
        raise QuizError("진행 중인 퀴즈 회차가 끝난 뒤 기준 시간을 변경할 수 있습니다.")

    common_question = validated_data.get("next_common_question", quiz_settings.next_common_question)
    common_question = common_question.strip()
    common_normalized = normalize_question(common_question)
    if common_question and QuizItem.objects.filter(
        round__team=locked_team, question_normalized=common_normalized
    ).exists():
        raise QuizError("이미 참가자에게 배정된 질문입니다. 다른 공통 질문을 입력해 주세요.")

    requested_enabled = validated_data.get("enabled", quiz_settings.enabled)
    if requested_enabled and not quiz_settings.enabled:
        total = Participant.objects.filter(team=locked_team).count()
        claimed = Participant.objects.filter(team=locked_team, claimed_by__isnull=False).count()
        if not total or total != claimed:
            raise QuizError("모든 참여자가 본인 확인을 마친 뒤 퀴즈 모드를 켤 수 있습니다.")
        if QuizRound.objects.filter(team=locked_team, status=QuizRound.Status.ACTIVE).exists():
            raise QuizError("기존 회차가 정산 또는 취소된 뒤 다시 활성화할 수 있습니다.")
        quiz_settings.next_round_starts_at = next_local_rotation(
            now,
            quiz_settings.quiz_timezone,
            rotation_hour,
        )
    elif requested_enabled and rotation_hour_changed:
        quiz_settings.next_round_starts_at = next_local_rotation(
            now,
            quiz_settings.quiz_timezone,
            rotation_hour,
        )
    elif not requested_enabled:
        quiz_settings.next_round_starts_at = None

    quiz_settings.enabled = requested_enabled
    quiz_settings.rotation_hour = rotation_hour
    quiz_settings.reference_days = reference_days
    quiz_settings.solve_days = solve_days
    quiz_settings.next_common_question = common_question
    quiz_settings.next_common_question_normalized = common_normalized
    quiz_settings.save()
    if requested_enabled:
        _mark_notification_keys_read([f"quiz:ready:{locked_team.id}:{locked_team.owner_id}"])
    publish_quiz_changed(locked_team)
    return quiz_settings


@transaction.atomic
def decide_collision(team, round_id, user, decision, now=None):
    now = now or timezone.now()
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    round_obj = QuizRound.objects.select_for_update().filter(pk=round_id, team=locked_team).first()
    if not round_obj:
        raise QuizError("퀴즈 회차를 찾을 수 없습니다.")
    if round_obj.collision_decision != QuizRound.CollisionDecision.PENDING:
        if round_obj.collision_decision == decision:
            return round_obj
        raise QuizError("이미 진행 여부가 확정된 회차입니다.")
    if now >= round_obj.reference_ends_at:
        _cancel_round(round_obj, "END_CONFLICT_NO_DECISION", now)
        raise QuizError("결정 가능 시간이 지났습니다.")
    if decision == QuizRound.CollisionDecision.PROCEED:
        round_obj.collision_decision = decision
        round_obj.collision_decided_at = now
        round_obj.collision_decided_by = user
        round_obj.save(
            update_fields=["collision_decision", "collision_decided_at", "collision_decided_by"]
        )
        _mark_notification_keys_read([f"quiz:{round_obj.id}:collision:{locked_team.owner_id}"])
        publish_quiz_changed(locked_team)
    elif decision == QuizRound.CollisionDecision.CANCEL:
        round_obj.collision_decided_at = now
        round_obj.collision_decided_by = user
        round_obj.save(update_fields=["collision_decided_at", "collision_decided_by"])
        _cancel_round(round_obj, "ADMIN_END_CONFLICT_CANCEL", now)
    else:
        raise QuizError("올바른 결정을 선택해 주세요.")
    return round_obj


@transaction.atomic
def confirm_reference_answer(team, item_id, user, answer, now=None):
    now = now or timezone.now()
    process_team_timeline(team.id, now, create_round=False)
    Team.objects.select_for_update().get(pk=team.pk)
    item = QuizItem.objects.select_for_update().select_related("round", "author").filter(
        pk=item_id, round__team=team, author__claimed_by=user
    ).first()
    if not item:
        raise QuizError("기준 답안 항목을 찾을 수 없습니다.")
    value = answer.strip()
    if not value:
        raise QuizError("기준 답안은 공백만으로 확정할 수 없습니다.")
    if item.reference_confirmed_at:
        if item.reference_answer == value:
            return item
        raise QuizError("이미 다른 기준 답안으로 확정했습니다.")
    if item.round.status != QuizRound.Status.ACTIVE or not (item.round.starts_at <= now < item.round.reference_ends_at):
        raise QuizError("기준 답안 입력기간이 아닙니다.")
    item.reference_answer = value
    item.reference_confirmed_at = now
    item.save(update_fields=["reference_answer", "reference_confirmed_at"])
    _mark_quiz_action_notifications_read(item.round_id, "reference", user.id)
    publish_quiz_changed(team)
    return item


@transaction.atomic
def save_solution_draft(team, item_id, user, answer, now=None):
    now = now or timezone.now()
    process_team_timeline(team.id, now, create_round=False)
    Team.objects.select_for_update().get(pk=team.pk)
    item = QuizItem.objects.select_for_update().select_related("round", "solver").filter(
        pk=item_id, round__team=team, solver__claimed_by=user
    ).first()
    if not item:
        raise QuizError("풀이 항목을 찾을 수 없습니다.")
    if item.round.status != QuizRound.Status.ACTIVE or not (
        item.round.reference_ends_at <= now < item.round.solve_ends_at
    ):
        raise QuizError("풀이기간이 아닙니다.")
    if item.round.collision_decision == QuizRound.CollisionDecision.PENDING:
        raise QuizError("관리자의 회차 진행 결정을 기다리고 있습니다.")
    if not item.reference_confirmed_at:
        raise QuizError("이번 회차에는 풀 수 있는 문제가 없습니다.")
    value = answer.strip()
    if value:
        item.solution_draft = value
        item.solution_draft_saved_at = now
        item.save(update_fields=["solution_draft", "solution_draft_saved_at"])
        _mark_quiz_action_notifications_read(item.round_id, "solve", user.id)
        publish_quiz_changed(team)
    return item


@transaction.atomic
def confirm_evaluation(team, item_id, user, score, now=None):
    now = now or timezone.now()
    process_team_timeline(team.id, now, create_round=False)
    Team.objects.select_for_update().get(pk=team.pk)
    item = QuizItem.objects.select_for_update().select_related("round", "author").filter(
        pk=item_id, round__team=team, author__claimed_by=user
    ).first()
    if not item:
        raise QuizError("평가 항목을 찾을 수 없습니다.")
    if item.round.status != QuizRound.Status.ACTIVE or not (
        item.round.solve_ends_at <= now < item.round.evaluation_ends_at
    ):
        raise QuizError("평가기간이 아닙니다.")
    if not item.solution_submitted_at:
        raise QuizError("평가할 제출 답안이 없습니다.")
    item.evaluation_score = score
    item.evaluated_at = now
    item.save(update_fields=["evaluation_score", "evaluated_at"])
    _mark_quiz_action_notifications_read(item.round_id, "evaluation", user.id)
    publish_quiz_changed(team)
    return item


def _round_phase(round_obj, now):
    if round_obj.status == QuizRound.Status.CANCELLED:
        return "CANCELLED"
    if round_obj.status == QuizRound.Status.SETTLED:
        return "SETTLED"
    if now < round_obj.reference_ends_at:
        return "REFERENCE"
    if now < round_obj.solve_ends_at:
        return "SOLVE"
    if now < round_obj.evaluation_ends_at:
        return "EVALUATION"
    return "SETTLING"


@transaction.atomic
def remind_pending_quiz_participants(team, round_id, now=None):
    now = now or timezone.now()
    process_team_timeline(team.id, now, create_round=False)
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    round_obj = QuizRound.objects.select_for_update().filter(
        pk=round_id,
        team=locked_team,
        status=QuizRound.Status.ACTIVE,
    ).first()
    if not round_obj:
        raise QuizError("진행 중인 퀴즈 회차를 찾을 수 없습니다.")

    phase = _round_phase(round_obj, now)
    items = list(
        QuizItem.objects.select_for_update()
        .filter(round=round_obj)
        .select_related("author", "solver")
    )
    if phase == "REFERENCE":
        targets = [
            (item.author.claimed_by_id, Notification.Kind.QUIZ_REFERENCE_OPEN)
            for item in items
            if not item.reference_confirmed_at and item.author.claimed_by_id
        ]
        action = "reference"
        title = "비밀 퀴즈 기준 답안을 입력해 주세요"
        body = "아직 기준 답안이 확정되지 않았습니다. 마감 전에 입력해 주세요."
    elif phase == "SOLVE":
        targets = [
            (item.solver.claimed_by_id, Notification.Kind.QUIZ_SOLVE_OPEN)
            for item in items
            if item.reference_confirmed_at
            and not item.solution_draft_saved_at
            and not item.settled_at
            and item.solver.claimed_by_id
        ]
        action = "solve"
        title = "비밀 퀴즈 답안을 저장해 주세요"
        body = "아직 저장된 풀이가 없습니다. 마감 전에 답안을 저장해 주세요."
    elif phase == "EVALUATION":
        targets = [
            (item.author.claimed_by_id, Notification.Kind.QUIZ_EVALUATION_OPEN)
            for item in items
            if item.solution_submitted_at
            and item.evaluation_score is None
            and not item.settled_at
            and item.author.claimed_by_id
        ]
        action = "evaluation"
        title = "비밀 퀴즈 평가를 저장해 주세요"
        body = "아직 평가 점수가 저장되지 않았습니다. 마감 전에 평가해 주세요."
    else:
        raise QuizError("현재 단계에는 재알림을 보낼 수 없습니다.")

    batch_id = uuid4().hex
    reminded_count = 0
    for recipient_id, kind in targets:
        _, created = create_quiz_notification(
            recipient_id=recipient_id,
            team=locked_team,
            kind=kind,
            title=title,
            body=body,
            dedupe_key=f"quiz:{round_obj.id}:{action}:manual:{batch_id}:{recipient_id}",
            path=f"/teams/{locked_team.code}/quiz",
            round_id=round_obj.id,
        )
        reminded_count += int(created)
    return {
        "round_id": round_obj.id,
        "phase": phase,
        "reminded_count": reminded_count,
    }


def participant_quiz_payload(team, user, now=None):
    now = now or timezone.now()
    process_team_timeline(team.id, now)
    participant = Participant.objects.filter(team=team, claimed_by=user).first()
    if not participant:
        raise QuizError("이 팀에서 본인 확인을 마친 참가자만 비밀 퀴즈를 사용할 수 있습니다.")
    active_rounds = list(QuizRound.objects.filter(team=team, status=QuizRound.Status.ACTIVE).order_by("sequence"))
    reference_task = None
    solve_task = None
    evaluation_task = None
    for round_obj in active_rounds:
        if round_obj.starts_at <= now < round_obj.reference_ends_at:
            item = QuizItem.objects.filter(round=round_obj, author=participant).first()
            if item:
                reference_task = {
                    "item_id": item.id,
                    "round_sequence": round_obj.sequence,
                    "phase": _round_phase(round_obj, now),
                    "decision_pending": round_obj.collision_decision == QuizRound.CollisionDecision.PENDING,
                    "question_kind": item.question_kind,
                    "question": item.question_snapshot,
                    "answer": item.reference_answer if item.reference_confirmed_at else "",
                    "confirmed": bool(item.reference_confirmed_at),
                    "ends_at": round_obj.reference_ends_at,
                }
        if (
            round_obj.reference_ends_at <= now < round_obj.solve_ends_at
            and round_obj.collision_decision != QuizRound.CollisionDecision.PENDING
        ):
            item = QuizItem.objects.filter(round=round_obj, solver=participant, reference_confirmed_at__isnull=False).select_related("author").first()
            if item:
                solve_task = {
                    "item_id": item.id,
                    "round_sequence": round_obj.sequence,
                    "question_kind": item.question_kind,
                    "question": item.question_snapshot,
                    "target_name": item.author.display_name,
                    "draft": item.solution_draft,
                    "ends_at": round_obj.solve_ends_at,
                }
        if round_obj.solve_ends_at <= now < round_obj.evaluation_ends_at:
            item = QuizItem.objects.filter(
                round=round_obj,
                author=participant,
                solution_submitted_at__isnull=False,
                settled_at__isnull=True,
            ).first()
            if item:
                evaluation_task = {
                    "item_id": item.id,
                    "round_sequence": round_obj.sequence,
                    "question": item.question_snapshot,
                    "reference_answer": item.reference_answer,
                    "solution_answer": item.solution_submitted,
                    "score": item.evaluation_score,
                    "ends_at": round_obj.evaluation_ends_at,
                }

    history = [
        {
            "item_id": item.id,
            "round_sequence": item.round.sequence,
            "question": item.question_snapshot,
            "reference_answer": item.reference_answer or None,
            "solution_answer": item.solution_submitted or None,
            "raw_score": item.raw_score,
            "settlement_kind": item.settlement_kind,
            "settled_at": item.settled_at,
        }
        for item in QuizItem.objects.filter(round__team=team, solver=participant, settled_at__isnull=False)
        .select_related("round")
        .order_by("-round__sequence")
    ]
    return {
        "team_code": team.code,
        "team_status": team.status,
        "server_now": now,
        "reference_task": reference_task,
        "solve_task": solve_task,
        "evaluation_task": evaluation_task,
        "history": history,
    }


def admin_quiz_payload(team, now=None):
    now = now or timezone.now()
    process_team_timeline(team.id, now)
    quiz_settings, _ = TeamQuizSettings.objects.get_or_create(team=team)
    active_rounds = list(QuizRound.objects.filter(team=team, status=QuizRound.Status.ACTIVE).order_by("sequence"))
    visible_rounds = active_rounds[-2:]
    rounds_payload = []
    for round_obj in reversed(visible_rounds):
        items = list(QuizItem.objects.filter(round=round_obj))
        total_count = len(items)
        reference_completed = sum(bool(item.reference_confirmed_at) for item in items)
        solve_eligible = reference_completed
        solution_saved = sum(
            bool(item.reference_confirmed_at and item.solution_draft_saved_at)
            for item in items
        )
        solution_submitted = sum(
            bool(item.reference_confirmed_at and item.solution_submitted_at)
            for item in items
        )
        evaluation_eligible = solution_submitted
        evaluation_completed = sum(
            bool(item.solution_submitted_at and item.evaluation_score is not None)
            for item in items
        )
        phase = _round_phase(round_obj, now)
        pending_by_phase = {
            "REFERENCE": total_count - reference_completed,
            "SOLVE": solve_eligible - solution_saved,
            "EVALUATION": evaluation_eligible - evaluation_completed,
        }
        rounds_payload.append(
            {
                "id": round_obj.id,
                "sequence": round_obj.sequence,
                "phase": phase,
                "starts_at": round_obj.starts_at,
                "reference_ends_at": round_obj.reference_ends_at,
                "solve_ends_at": round_obj.solve_ends_at,
                "evaluation_ends_at": round_obj.evaluation_ends_at,
                "collision_decision": round_obj.collision_decision,
                "progress": {
                    "reference": {"completed": reference_completed, "total": total_count},
                    "solution_saved": {"completed": solution_saved, "total": solve_eligible},
                    "solution_submitted": {
                        "completed": solution_submitted,
                        "total": solve_eligible,
                    },
                    "evaluation": {
                        "completed": evaluation_completed,
                        "total": evaluation_eligible,
                    },
                },
                "pending_count": pending_by_phase.get(phase, 0),
                "can_remind": phase in pending_by_phase,
            }
        )
    pending_round = next(
        (round_obj for round_obj in active_rounds if round_obj.collision_decision == QuizRound.CollisionDecision.PENDING),
        None,
    )
    return {
        "team_code": team.code,
        "team_status": team.status,
        "enabled": quiz_settings.enabled,
        "quiz_timezone": quiz_settings.quiz_timezone,
        "rotation_hour": quiz_settings.rotation_hour,
        "rotation_hour_locked": bool(active_rounds),
        "reference_days": quiz_settings.reference_days,
        "solve_days": quiz_settings.solve_days,
        "next_common_question": quiz_settings.next_common_question,
        "next_round_starts_at": quiz_settings.next_round_starts_at,
        "next_round_collision": preview_collision(team, quiz_settings),
        "rounds": rounds_payload,
        "pending_decision": (
            {"round_id": pending_round.id, "reference_ends_at": pending_round.reference_ends_at}
            if pending_round
            else None
        ),
    }


def has_pending_reference_answer(user, now=None):
    now = now or timezone.now()
    return QuizItem.objects.filter(
        author__claimed_by=user,
        round__status=QuizRound.Status.ACTIVE,
        round__starts_at__lte=now,
        round__reference_ends_at__gt=now,
        reference_confirmed_at__isnull=True,
    ).exists()


def has_pending_solve_reminder(user, now=None):
    now = now or timezone.now()
    return QuizItem.objects.filter(
        solver__claimed_by=user,
        round__status=QuizRound.Status.ACTIVE,
        round__collision_decision__in=[
            QuizRound.CollisionDecision.NOT_REQUIRED,
            QuizRound.CollisionDecision.PROCEED,
        ],
        round__reference_ends_at__lte=now,
        round__solve_ends_at__gt=now,
        round__solve_ends_at__lte=now + timedelta(hours=24),
        reference_confirmed_at__isnull=False,
        solution_draft_saved_at__isnull=True,
    ).exists()


@transaction.atomic
def prepare_planned_end_change(team, planned_end_date, confirmed=False, now=None):
    now = now or timezone.now()
    quiz_settings = TeamQuizSettings.objects.select_for_update().filter(team=team).first()
    if not quiz_settings or not quiz_settings.quiz_timezone:
        return
    rounds = list(
        QuizRound.objects.select_for_update().filter(team=team, status=QuizRound.Status.ACTIVE)
    )
    for round_obj in rounds:
        collides = round_collides_with_end(team, round_obj, planned_end_date)
        if round_obj.starts_at <= now < round_obj.reference_ends_at:
            if collides and round_obj.collision_decision == QuizRound.CollisionDecision.NOT_REQUIRED:
                round_obj.collision_decision = QuizRound.CollisionDecision.PENDING
                round_obj.save(update_fields=["collision_decision"])
                create_quiz_notification(
                    recipient_id=team.owner_id,
                    team=team,
                    kind=Notification.Kind.QUIZ_END_CONFLICT,
                    title="퀴즈 일정과 종료 예정일이 겹쳐요",
                    body="입력기간이 끝나기 전에 이번 회차의 진행 여부를 결정해 주세요.",
                    dedupe_key=f"quiz:{round_obj.id}:collision:{team.owner_id}",
                    path=f"/teams/{team.code}/admin/quiz",
                    round_id=round_obj.id,
                )
            elif not collides and round_obj.collision_decision == QuizRound.CollisionDecision.PENDING:
                round_obj.collision_decision = QuizRound.CollisionDecision.NOT_REQUIRED
                round_obj.save(update_fields=["collision_decision"])
                _mark_notification_keys_read([f"quiz:{round_obj.id}:collision:{team.owner_id}"])
        elif round_obj.reference_ends_at <= now < round_obj.solve_ends_at and collides and not confirmed:
            raise QuizConflictConfirmationRequired(round_obj.id)
    publish_quiz_changed(team)


@transaction.atomic
def finalize_for_team_end(team, now=None):
    now = now or timezone.now()
    process_team_timeline(team.id, now, create_round=True)
    for round_obj in QuizRound.objects.select_for_update().filter(team=team, status=QuizRound.Status.ACTIVE):
        round_obj.status = QuizRound.Status.CANCELLED
        round_obj.cancel_reason = "TEAM_ENDED"
        round_obj.cancelled_at = now
        round_obj.save(update_fields=["status", "cancel_reason", "cancelled_at"])
    quiz_settings = TeamQuizSettings.objects.select_for_update().filter(team=team).first()
    if quiz_settings:
        quiz_settings.enabled = False
        quiz_settings.next_round_starts_at = None
        quiz_settings.save(update_fields=["enabled", "next_round_starts_at", "updated_at"])


def participant_quiz_rate(participant):
    totals = QuizItem.objects.filter(solver=participant, settled_at__isnull=False).aggregate(
        raw=Sum("raw_score", filter=Q(rate_max_score=5)),
        maximum=Sum("rate_max_score"),
    )
    maximum = totals["maximum"] or 0
    if maximum == 0:
        return None
    return round(((totals["raw"] or 0) / maximum) * 100, 1)
