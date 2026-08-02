import logging
import math
import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.accounts.push import send_web_push
from apps.chat.models import Notification
from apps.realtime.events import publish_user_events_on_commit

from .models import Participant, Team


logger = logging.getLogger(__name__)
# LOW_SCORE_REVEAL_EMOJIS = ("💀", "☠️", "☢️", "☣️", "🚨", "💣", "🫠", "🤡", "🤢", "💥", "⛔", "👺")
LOW_SCORE_REVEAL_EMOJIS = ("💀", "☠️")


def low_score_reveal_settings_payload(team):
    return {
        "low_score_reveal_enabled": team.low_score_reveal_enabled,
        "low_score_reveal_interval_days": team.low_score_reveal_interval_days,
        "low_score_reveal_percentage": team.low_score_reveal_percentage,
        "low_score_reveal_timezone": team.low_score_reveal_timezone,
        "low_score_reveal_next_at": team.low_score_reveal_next_at,
    }


def next_local_noon(*, timezone_name, now=None):
    now = now or timezone.now()
    local_timezone = ZoneInfo(timezone_name)
    local_now = now.astimezone(local_timezone)
    candidate = datetime.combine(local_now.date(), time(hour=12), tzinfo=local_timezone)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.get_current_timezone())


def _next_interval_noon(*, current_at, interval_days, timezone_name, now):
    local_timezone = ZoneInfo(timezone_name)
    candidate_date = current_at.astimezone(local_timezone).date() + timedelta(days=interval_days)
    candidate = datetime.combine(candidate_date, time(hour=12), tzinfo=local_timezone)
    while candidate <= now.astimezone(local_timezone):
        candidate_date += timedelta(days=interval_days)
        candidate = datetime.combine(candidate_date, time(hour=12), tzinfo=local_timezone)
    return candidate.astimezone(timezone.get_current_timezone())


@transaction.atomic
def update_low_score_reveal_settings(*, team, enabled, interval_days, percentage, timezone_name):
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    if locked_team.status != Team.Status.ACTIVE:
        raise ValueError("진행 중인 팀에서만 하위 활동 참여자 공개 설정을 변경할 수 있습니다.")

    schedule_changed = (
        not locked_team.low_score_reveal_enabled
        or locked_team.low_score_reveal_interval_days != interval_days
        or locked_team.low_score_reveal_percentage != percentage
        or locked_team.low_score_reveal_timezone != timezone_name
    )
    locked_team.low_score_reveal_enabled = enabled
    locked_team.low_score_reveal_interval_days = interval_days
    locked_team.low_score_reveal_percentage = percentage
    locked_team.low_score_reveal_timezone = timezone_name
    if not enabled:
        locked_team.low_score_reveal_next_at = None
    elif schedule_changed or locked_team.low_score_reveal_next_at is None:
        locked_team.low_score_reveal_next_at = next_local_noon(timezone_name=timezone_name)
    locked_team.save(
        update_fields=[
            "low_score_reveal_enabled",
            "low_score_reveal_interval_days",
            "low_score_reveal_percentage",
            "low_score_reveal_timezone",
            "low_score_reveal_next_at",
            "updated_at",
        ]
    )
    return locked_team


def _select_low_score_participants(participants, percentage):
    if not participants:
        return []

    count = max(1, math.ceil(len(participants) * percentage / 100))
    ordered = sorted(participants, key=lambda participant: (participant.leaderboard_score, participant.id))
    cutoff_score = ordered[count - 1].leaderboard_score
    selected = [participant for participant in ordered if participant.leaderboard_score < cutoff_score]
    tied = [participant for participant in ordered if participant.leaderboard_score == cutoff_score]
    random.shuffle(tied)
    selected.extend(tied[: count - len(selected)])
    random.shuffle(selected)
    return selected


def _notification_content(selected_participants):
    count = len(selected_participants)
    title = f"🚨🚨 하위 {count}인 공개 🚨🚨"
    lines = [
        f"게임 참여자들 중 활동이 저조한 {count}인을 공개합니다!",
        "다들 마니또 활동에 적극적으로 참여해 주세요!",
        *[
            f"{random.choice(LOW_SCORE_REVEAL_EMOJIS)}{participant.display_name}"
            for participant in selected_participants
        ],
    ]
    return title, "\n".join(lines)


def publish_low_score_reveal(*, team_id, now=None, force=False):
    now = now or timezone.now()
    with transaction.atomic():
        team = Team.objects.select_for_update().filter(pk=team_id, status=Team.Status.ACTIVE).first()
        if team is None:
            return None
        if not force and (
            not team.low_score_reveal_enabled
            or team.low_score_reveal_next_at is None
            or team.low_score_reveal_next_at > now
        ):
            return None

        participants = list(Participant.objects.filter(team=team).order_by("id"))
        selected = _select_low_score_participants(participants, team.low_score_reveal_percentage)
        if not selected:
            return None

        title, body = _notification_content(selected)
        recipient_ids = list(
            Participant.objects.filter(team=team, claimed_by__isnull=False)
            .order_by()
            .values_list("claimed_by_id", flat=True)
            .distinct()
        )
        notifications = [
            Notification(
                recipient_id=recipient_id,
                team=team,
                kind=Notification.Kind.LOW_SCORE_REVEAL,
                title=title,
                body=body,
                data={"low_score_reveal": True, "count": len(selected)},
            )
            for recipient_id in recipient_ids
        ]
        Notification.objects.bulk_create(notifications)
        publish_user_events_on_commit(recipient_ids, "notifications.changed")

        if not force:
            team.low_score_reveal_next_at = _next_interval_noon(
                current_at=team.low_score_reveal_next_at,
                interval_days=team.low_score_reveal_interval_days,
                timezone_name=team.low_score_reveal_timezone,
                now=now,
            )
            team.save(update_fields=["low_score_reveal_next_at", "updated_at"])

        result = {
            "team_id": team.id,
            "team_code": team.code,
            "title": title,
            "body": body,
            "selected_names": [participant.display_name for participant in selected],
            "notification_count": len(notifications),
            "recipient_ids": recipient_ids,
            "next_at": team.low_score_reveal_next_at,
        }

    result["push_delivery_count"] = sum(
        send_web_push(
            user_id=recipient_id,
            title=title,
            body=body,
            path="/notifications",
        )
        for recipient_id in recipient_ids
    )
    return result


def process_low_score_reveals():
    now = timezone.now()
    team_ids = list(
        Team.objects.filter(
            status=Team.Status.ACTIVE,
            low_score_reveal_enabled=True,
            low_score_reveal_next_at__lte=now,
        ).values_list("id", flat=True)
    )
    published_count = 0
    for team_id in team_ids:
        try:
            if publish_low_score_reveal(team_id=team_id, now=now):
                published_count += 1
        except Exception:
            logger.exception("Low score reveal failed: team_id=%s", team_id)
    return published_count
