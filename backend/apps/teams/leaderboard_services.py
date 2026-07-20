"""게임 프로필, 점수, 공개 순위를 다루는 서버 전용 서비스."""

import random
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .leaderboard_config import (
    CARED_FOR_TO_MANITO_MULTIPLIER,
    CHAT_LIKE_COOLDOWN_HOURS,
    CHAT_LIKE_POINTS,
    CHAT_MESSAGE_COOLDOWN_MINUTES,
    CHAT_MESSAGE_DAILY_LIMIT,
    CHAT_MESSAGE_POINTS,
    LEADERBOARD_AVATAR_KEYS,
    LEADERBOARD_NICKNAMES,
    TEAM_VISIT_COOLDOWN_HOURS,
    TEAM_VISIT_POINTS,
)
from .models import LeaderboardSnapshot, Participant, ScoreEvent, Team


def _profile_pairs(*, randomize):
    """별명을 고르게 섞고, 이름 끝의 캐릭터와 같은 프리셋만 조합한다."""
    nicknames = list(LEADERBOARD_NICKNAMES)
    avatar_keys_by_character = {
        "마니": [avatar_key for avatar_key in LEADERBOARD_AVATAR_KEYS if avatar_key.startswith("mani-")],
        "클로디": [avatar_key for avatar_key in LEADERBOARD_AVATAR_KEYS if avatar_key.startswith("clodi-")],
    }
    if randomize:
        random.shuffle(nicknames)
        for avatar_keys in avatar_keys_by_character.values():
            random.shuffle(avatar_keys)

    nickname_indexes = {"마니": {}, "클로디": {}}
    character_counts = {"마니": 0, "클로디": 0}
    for nickname in nicknames:
        character = "클로디" if nickname.endswith("클로디") else "마니"
        nickname_indexes[character][nickname] = character_counts[character]
        character_counts[character] += 1

    pairs = []
    for avatar_round in range(9):
        for nickname in nicknames:
            character = "클로디" if nickname.endswith("클로디") else "마니"
            avatar_keys = avatar_keys_by_character[character]
            avatar_index = (nickname_indexes[character][nickname] + avatar_round) % len(avatar_keys)
            pairs.append((nickname, avatar_keys[avatar_index]))
    return pairs


def assign_leaderboard_profiles(participants, *, randomize=True):
    """참여자별 게임 프로필을 배정한다. 최초 123명은 조합이 겹치지 않는다."""
    pairs = _profile_pairs(randomize=randomize)
    for index, participant in enumerate(participants):
        nickname, avatar_key = pairs[index % len(pairs)]
        participant.leaderboard_nickname = nickname
        participant.leaderboard_avatar_key = avatar_key
    Participant.objects.bulk_update(participants, ["leaderboard_nickname", "leaderboard_avatar_key"])


def _is_active(team):
    return team.status == Team.Status.ACTIVE


def _is_cared_for_by(participant, counterpart):
    return counterpart.assigned_to_id == participant.id


def _award(*, team, participant, event_type, points, room_id="", source_message=None):
    ScoreEvent.objects.create(
        team=team,
        participant=participant,
        event_type=event_type,
        room_id=room_id,
        source_message=source_message,
        points=points,
    )
    Participant.objects.filter(pk=participant.pk).update(leaderboard_score=F("leaderboard_score") + points)


@transaction.atomic
def award_message_score(*, message, room_id):
    """동일 메시지의 중복 점수와 채팅방별 제한을 서버에서 막는다."""
    team = Team.objects.select_for_update().get(pk=message.team_id)
    participant = Participant.objects.select_for_update().get(pk=message.sender_id)
    if not _is_active(team) or ScoreEvent.objects.filter(source_message=message).exists():
        return False

    now = timezone.now()
    base_events = ScoreEvent.objects.filter(
        team=team, participant=participant, event_type=ScoreEvent.Type.CHAT_MESSAGE, room_id=room_id
    )
    if base_events.filter(created_at__gte=now - timedelta(minutes=CHAT_MESSAGE_COOLDOWN_MINUTES)).exists():
        return False
    if base_events.filter(created_at__date=timezone.localdate(now)).count() >= CHAT_MESSAGE_DAILY_LIMIT:
        return False
    multiplier = CARED_FOR_TO_MANITO_MULTIPLIER if _is_cared_for_by(participant, message.recipient) else 1
    _award(
        team=team,
        participant=participant,
        event_type=ScoreEvent.Type.CHAT_MESSAGE,
        points=CHAT_MESSAGE_POINTS * multiplier,
        room_id=room_id,
        source_message=message,
    )
    return True


@transaction.atomic
def award_like_score(*, room):
    team = Team.objects.select_for_update().get(pk=room.team.id)
    participant = Participant.objects.select_for_update().get(pk=room.me.id)
    counterpart = Participant.objects.select_for_update().get(pk=room.counterpart.id)
    if not _is_active(team):
        raise ValueError("게임이 종료된 뒤에는 좋아요를 보낼 수 없습니다.")
    if counterpart.claimed_by_id is None:
        raise PermissionError("상대방이 아직 본인 확인을 완료하지 않았습니다.")
    latest_event = ScoreEvent.objects.filter(
        team=team, participant=participant, event_type=ScoreEvent.Type.CHAT_LIKE, room_id=room.room_id
    ).order_by("-created_at").first()
    next_available_at = None
    if latest_event:
        next_available_at = latest_event.created_at + timedelta(hours=CHAT_LIKE_COOLDOWN_HOURS)
        if next_available_at > timezone.now():
            return False, next_available_at
    multiplier = CARED_FOR_TO_MANITO_MULTIPLIER if _is_cared_for_by(participant, counterpart) else 1
    _award(
        team=team,
        participant=participant,
        event_type=ScoreEvent.Type.CHAT_LIKE,
        points=CHAT_LIKE_POINTS * multiplier,
        room_id=room.room_id,
    )
    created_event = ScoreEvent.objects.filter(
        team=team, participant=participant, event_type=ScoreEvent.Type.CHAT_LIKE, room_id=room.room_id
    ).latest("created_at")
    return True, created_event.created_at + timedelta(hours=CHAT_LIKE_COOLDOWN_HOURS)


@transaction.atomic
def award_visit_score(*, team, user):
    """Claim 완료 참여자만 팀 접속 점수를 받는다. 관리자는 조회만 가능하다."""
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    participant = Participant.objects.select_for_update().filter(team=locked_team, claimed_by=user).first()
    if not participant or not _is_active(locked_team):
        return False
    now = timezone.now()
    if participant.last_visit_score_at and participant.last_visit_score_at + timedelta(hours=TEAM_VISIT_COOLDOWN_HOURS) > now:
        return False
    _award(team=locked_team, participant=participant, event_type=ScoreEvent.Type.TEAM_VISIT, points=TEAM_VISIT_POINTS)
    participant.last_visit_score_at = now
    participant.save(update_fields=["last_visit_score_at"])
    return True


@transaction.atomic
def generate_leaderboard_snapshot(team):
    """점수 내림차순, 참가자 생성 순서로 안정 정렬한 공개 스냅샷을 만든다."""
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    participants = list(Participant.objects.filter(team=locked_team).order_by("-leaderboard_score", "id")[:123])
    rankings = []
    previous_score = None
    rank = 0
    for position, participant in enumerate(participants, start=1):
        if participant.leaderboard_score != previous_score:
            rank = position
            previous_score = participant.leaderboard_score
        rankings.append({"participant_id": participant.id, "rank": rank})
    snapshot, _ = LeaderboardSnapshot.objects.update_or_create(
        team=locked_team,
        defaults={"rankings": rankings, "generated_at": timezone.now()},
    )
    return snapshot


def generate_active_leaderboard_snapshots():
    return sum(1 for team in Team.objects.filter(status=Team.Status.ACTIVE) if generate_leaderboard_snapshot(team))


def results_released(team):
    return team.status == Team.Status.ENDED and team.reveal_status in {
        Team.RevealStatus.AUTO_RELEASED,
        Team.RevealStatus.MANUAL_RELEASED,
    }


def leaderboard_payload(*, team, user):
    snapshot = LeaderboardSnapshot.objects.filter(team=team).first() or generate_leaderboard_snapshot(team)
    participant_ids = [entry["participant_id"] for entry in snapshot.rankings]
    participants = Participant.objects.in_bulk(participant_ids)
    my_participant_id = Participant.objects.filter(team=team, claimed_by=user).values_list("id", flat=True).first()
    released = results_released(team)
    entries = []
    for ranking in snapshot.rankings:
        participant = participants.get(ranking["participant_id"])
        if not participant:
            continue
        entry = {
            "rank": ranking["rank"],
            "name": participant.display_name if released else participant.leaderboard_nickname,
            "game_nickname": participant.leaderboard_nickname,
            "avatar_key": participant.leaderboard_avatar_key,
            "is_me": participant.id == my_participant_id,
        }
        if released:
            entry["score"] = participant.leaderboard_score
        entries.append(entry)
    next_update_at = snapshot.generated_at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return {
        "team_code": team.code,
        "updated_at": snapshot.generated_at,
        "next_update_at": next_update_at,
        "results_released": released,
        "entries": entries,
    }
