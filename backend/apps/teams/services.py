import random
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.push import send_web_push_async
from apps.realtime.events import publish_user_events_on_commit
from .models import Participant, Team
from .leaderboard_services import assign_leaderboard_profiles, generate_leaderboard_snapshot


MAX_MATCHING_ATTEMPTS = 10_000


class MatchingError(Exception):
    """지정한 제약 조건을 만족하는 마니또 배정을 만들 수 없을 때 발생한다."""


class ClaimError(Exception):
    """참여자 Claim 조건을 충족하지 못했을 때 발생한다."""


class AdminAccessError(Exception):
    """팀 생성자에게만 허용된 관리자 작업이 거부됐을 때 발생한다."""




@transaction.atomic
def create_team_with_matching(*, owner, validated_data):
    """팀·참여자·마니또 배정을 하나의 트랜잭션으로 생성한다."""
    team = Team(
        code=validated_data["code"],
        owner=owner,
        rules=validated_data["rules"],
        reciprocal_ratio=validated_data["reciprocal_ratio"],
        status=Team.Status.ACTIVE,
        reveal_mode=validated_data.get("reveal_mode", Team.RevealMode.AUTO),
        reveal_status=(
            Team.RevealStatus.MANUAL_PENDING
            if validated_data.get("reveal_mode", Team.RevealMode.AUTO) == Team.RevealMode.ADMIN
            else Team.RevealStatus.AUTO_RELEASED
        ),
        planned_end_date=validated_data.get("planned_end_date"),
        planned_end_timezone=validated_data.get("planned_end_timezone", ""),
    )
    team.save()

    participant_names = validated_data["parsed_participant_names"]
    owner_nickname = owner.kakao_nickname
    participants = [
        Participant(
            team=team,
            display_name=name,
            claimed_by=owner if validated_data["is_participating"] and name == owner_nickname else None,
        )
        for name in participant_names
    ]
    participants = Participant.objects.bulk_create(participants)
    assign_leaderboard_profiles(participants)
    assign_manitos(participants, team.reciprocal_ratio)
    generate_leaderboard_snapshot(team)

    return team


def assign_manitos(participants, reciprocal_ratio):
    """자기 지목과 과도한 상호 지목을 배제한 순열을 찾아 일괄 저장한다."""
    participant_count = len(participants)
    if participant_count < 2:
        raise MatchingError("마니또 배정에는 최소 2명이 필요합니다.")
    if participant_count == 2 and reciprocal_ratio < 100:
        raise MatchingError("2명 팀은 상호 지목 비율을 100%로 설정해야 합니다.")

    target_indexes = list(range(participant_count))
    for _ in range(MAX_MATCHING_ATTEMPTS):
        random.shuffle(target_indexes)

        if any(source_index == target_index for source_index, target_index in enumerate(target_indexes)):
            continue

        reciprocal_pair_count = sum(
            1
            for source_index, target_index in enumerate(target_indexes)
            if source_index < target_index and target_indexes[target_index] == source_index
        )
        reciprocal_participant_count = reciprocal_pair_count * 2
        if reciprocal_participant_count * 100 > reciprocal_ratio * participant_count:
            continue

        for source_index, target_index in enumerate(target_indexes):
            participants[source_index].assigned_to = participants[target_index]
        Participant.objects.bulk_update(participants, ["assigned_to"])
        return

    raise MatchingError("주어진 상호 지목 비율로 배정을 만들지 못했습니다. 다시 시도해 주세요.")


@transaction.atomic
def claim_participant(*, team, user, participant_id):
    """미확인 참여자 한 명을 현재 사용자에게 안전하게 연결한다."""
    Team.objects.select_for_update().get(pk=team.pk)

    existing_claim = (
        Participant.objects.select_for_update()
        .filter(team=team, claimed_by=user)
        .first()
    )
    if existing_claim:
        raise ClaimError("이 팀에서 이미 다른 이름을 확인했습니다.")

    try:
        participant = (
            Participant.objects.select_for_update()
            .get(pk=participant_id, team=team)
        )
    except Participant.DoesNotExist as error:
        raise ClaimError("선택한 참여자를 찾을 수 없습니다.") from error

    if participant.claimed_by_id is not None:
        raise ClaimError("이미 다른 사용자가 확인한 이름입니다.")
    if participant.assigned_to_id is None:
        raise ClaimError("마니또 배정이 완료되지 않았습니다.")

    participant.claimed_by = user
    try:
        # 팀별 사용자 Claim 유니크 제약의 경쟁 충돌을 Claim 오류로 변환한다.
        with transaction.atomic():
            participant.save(update_fields=["claimed_by"])
    except IntegrityError as error:
        raise ClaimError("이 팀에서 이미 다른 이름을 확인했습니다.") from error
    create_claim_notifications(team=team, participant=participant, claiming_user=user)
    return participant


def get_team_dashboard(team):
    """관리자만 볼 수 있는 참여 진행 현황을 계산한다."""
    participants = Participant.objects.filter(team=team)
    claimed_participants = list(
        participants.filter(claimed_by__isnull=False)
        .select_related("claimed_by")
        .order_by("id")
    )
    unclaimed_names = list(
        participants.filter(claimed_by__isnull=True).order_by("id").values_list("display_name", flat=True)
    )
    total_count = participants.count()
    dashboard = {
        "team_code": team.code,
        "status": team.status,
        "reveal_mode": team.reveal_mode,
        "reveal_status": team.reveal_status,
        "planned_end_date": team.planned_end_date,
        "planned_end_timezone": team.planned_end_timezone,
        "rules": team.rules,
        "total_count": total_count,
        "claimed_count": len(claimed_participants),
        "unclaimed_names": unclaimed_names,
        "claimed_participants": [
            {
                "id": participant.id,
                "display_name": participant.display_name,
                "claimed_by_nickname": participant.claimed_by.kakao_nickname,
            }
            for participant in claimed_participants
        ],
    }
    if team.status == Team.Status.ENDED and team.reveal_mode == Team.RevealMode.ADMIN:
        dashboard["reveal_assignments"] = [
            {
                "from_name": participant.display_name,
                "to_name": participant.assigned_to.display_name,
            }
            for participant in participants.select_related("assigned_to").order_by("id")
            if participant.assigned_to_id is not None
        ]
    return dashboard


def get_my_teams(user):
    """사용자가 소유하거나 Claim한 팀을 대시보드 카드용 정보로 반환한다."""
    from apps.chat.models import Message

    teams = (
        Team.objects.filter(Q(owner=user) | Q(participants__claimed_by=user))
        .distinct()
        .order_by("status", "-updated_at")
    )
    result = []
    for team in teams:
        participant = Participant.objects.filter(team=team, claimed_by=user).first()
        if team.status == Team.Status.ACTIVE:
            result_status = "ACTIVE"
        elif team.reveal_status == Team.RevealStatus.MANUAL_PENDING:
            result_status = "MANUAL_PENDING"
        else:
            result_status = "RESULT_AVAILABLE"

        result.append(
            {
                "code": team.code,
                "status": team.status,
                "is_owner": team.owner_id == user.id,
                "claim_status": "CLAIMED" if participant else "UNCLAIMED",
                "reveal_mode": team.reveal_mode,
                "reveal_status": team.reveal_status,
                "result_status": result_status,
                "countdown": get_team_countdown(team),
                "unread_count": (
                    Message.objects.filter(recipient=participant, read_at__isnull=True).count()
                    if participant
                    else 0
                ),
            }
        )
    return result


def get_team_countdown(team):
    """관리자가 정한 지역 날짜 기준의 안내용 카운트다운을 반환한다."""
    if team.planned_end_date is None:
        return {
            "team_code": team.code,
            "planned_end_date": None,
            "planned_end_timezone": None,
            "remaining": None,
            "remaining_days": None,
        }

    try:
        end_timezone = ZoneInfo(team.planned_end_timezone or settings.TIME_ZONE)
    except ZoneInfoNotFoundError:
        end_timezone = timezone.get_current_timezone()

    today = timezone.now().astimezone(end_timezone).date()
    remaining_days = (team.planned_end_date - today).days
    if remaining_days <= 0:
        remaining = "D-Day!"
        remaining_days = 0
    else:
        remaining = f"D-{remaining_days}"

    return {
        "team_code": team.code,
        "planned_end_date": team.planned_end_date,
        "planned_end_timezone": team.planned_end_timezone,
        "remaining": remaining,
        "remaining_days": remaining_days,
    }


@transaction.atomic
def update_team_planned_end(*, team, planned_end_date, planned_end_timezone):
    """진행 중인 팀의 안내용 종료 예정일을 수정한다."""
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    if locked_team.status != Team.Status.ACTIVE:
        raise AdminAccessError("종료된 팀의 종료 예정일은 수정할 수 없습니다.")

    locked_team.planned_end_date = planned_end_date
    locked_team.planned_end_timezone = planned_end_timezone
    locked_team.save(update_fields=["planned_end_date", "planned_end_timezone", "updated_at"])
    return locked_team


@transaction.atomic
def update_team_reveal_mode(*, team, reveal_mode):
    """진행 중인 팀의 결과 공개 방식을 수정한다."""
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    if locked_team.status != Team.Status.ACTIVE:
        raise AdminAccessError("게임 종료 후에는 결과 공개 방식을 수정할 수 없습니다.")

    locked_team.reveal_mode = reveal_mode
    locked_team.reveal_status = (
        Team.RevealStatus.MANUAL_PENDING
        if reveal_mode == Team.RevealMode.ADMIN
        else Team.RevealStatus.AUTO_RELEASED
    )
    locked_team.save(update_fields=["reveal_mode", "reveal_status", "updated_at"])
    return locked_team


@transaction.atomic
def update_team_rules(*, team, rules):
    """진행 중인 팀의 참가자 안내 규칙을 수정한다."""
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    if locked_team.status != Team.Status.ACTIVE:
        raise AdminAccessError("종료된 팀의 규칙은 수정할 수 없습니다.")

    locked_team.rules = rules
    locked_team.save(update_fields=["rules", "updated_at"])
    return locked_team


@transaction.atomic
def create_team_announcement(*, team, message):
    """진행 중인 팀의 Claim 완료 참여자에게 앱 내 공지를 보낸다."""
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    if locked_team.status != Team.Status.ACTIVE:
        raise AdminAccessError("진행 중인 팀에만 알림을 보낼 수 있습니다.")

    from apps.chat.models import Notification

    recipients = (
        Participant.objects.filter(team=locked_team, claimed_by__isnull=False)
        .exclude(claimed_by=locked_team.owner)
        .select_related("claimed_by")
    )
    notifications = [
        Notification(
            recipient=participant.claimed_by,
            team=locked_team,
            kind=Notification.Kind.TEAM_ANNOUNCEMENT,
            title="팀 관리자 알림",
            body=message,
            data={"announcement": True},
        )
        for participant in recipients
    ]
    Notification.objects.bulk_create(notifications)
    for notification in notifications:
        transaction.on_commit(
            lambda notification=notification: send_web_push_async(
                user_id=notification.recipient_id,
                title=notification.title,
                body=notification.body,
                path=f"/teams/{locked_team.code}",
            )
        )
    publish_user_events_on_commit(
        [notification.recipient_id for notification in notifications],
        "notifications.changed",
    )
    return len(notifications)


@transaction.atomic
def delete_team(*, team):
    """오생성 팀을 안전 조건 하에서 영구 삭제한다."""
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    if locked_team.status != Team.Status.ACTIVE:
        raise AdminAccessError("진행 중인 팀만 삭제할 수 있습니다.")
    if (
        Participant.objects.filter(team=locked_team, claimed_by__isnull=False)
        .exclude(claimed_by=locked_team.owner)
        .exists()
    ):
        raise AdminAccessError("다른 참여자가 확인한 팀은 삭제할 수 없습니다.")

    from apps.chat.scheduler import purge_team_chat_data

    purge_team_chat_data(locked_team.id)
    locked_team.delete()


@transaction.atomic
def release_manual_results(*, team):
    """외부 공개 행사가 끝난 뒤 참가자 결과 조회를 열어 준다."""
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    if locked_team.status != Team.Status.ENDED:
        raise AdminAccessError("게임 종료 후에만 결과를 공개할 수 있습니다.")
    if locked_team.reveal_mode != Team.RevealMode.ADMIN:
        raise AdminAccessError("관리자 외부 공개 팀만 결과를 열 수 있습니다.")
    if locked_team.reveal_status != Team.RevealStatus.MANUAL_PENDING:
        raise AdminAccessError("이미 참가자 결과가 공개되었습니다.")

    locked_team.reveal_status = Team.RevealStatus.MANUAL_RELEASED
    locked_team.save(update_fields=["reveal_status", "updated_at"])
    return locked_team


def create_result_notifications(team):
    """결과를 앱에서 확인할 수 있게 된 Claim 완료 참가자에게 알림을 생성한다."""
    from apps.chat.models import Notification

    notifications = [
        Notification(
            recipient=participant.claimed_by,
            team=team,
            kind=Notification.Kind.RESULT_AVAILABLE,
            title="마니또 결과 공개",
            body="이제 앱에서 내 마니또 결과를 확인할 수 있습니다.",
        )
        for participant in Participant.objects.filter(team=team, claimed_by__isnull=False).select_related(
            "claimed_by"
        )
    ]
    Notification.objects.bulk_create(notifications)
    for notification in notifications:
        transaction.on_commit(
            lambda notification=notification: send_web_push_async(
                user_id=notification.recipient_id,
                title=notification.title,
                body=notification.body,
                path=f"/teams/{team.code}/reveal",
            )
        )
    recipient_ids = [notification.recipient_id for notification in notifications]
    publish_user_events_on_commit(recipient_ids, "notifications.changed")
    publish_user_events_on_commit(recipient_ids, "chat.rooms.changed")


def create_claim_notifications(*, team, participant, claiming_user):
    """참여 확인 완료 사실을 관리자에게만 알린다."""
    from apps.chat.models import Notification

    recipient_ids = {team.owner_id}
    recipient_ids.discard(claiming_user.id)

    notifications = [
        Notification(
            recipient_id=recipient_id,
            team=team,
            kind=Notification.Kind.PARTICIPANT_CLAIMED,
            title="참여자 본인 확인 완료",
            body=f"{participant.display_name} 님이 본인 확인을 완료했습니다.",
        )
        for recipient_id in recipient_ids
    ]
    Notification.objects.bulk_create(notifications)
    for notification in notifications:
        transaction.on_commit(
            lambda notification=notification: send_web_push_async(
                user_id=notification.recipient_id,
                title=notification.title,
                body=notification.body,
                path=f"/teams/{team.code}",
            )
        )
    recipient_ids = [notification.recipient_id for notification in notifications]
    publish_user_events_on_commit(recipient_ids, "notifications.changed")
    publish_user_events_on_commit(
        [claiming_user.id, *recipient_ids],
        "chat.rooms.changed",
    )


@transaction.atomic
def reset_participant_claim(*, team, participant_id):
    """오선택된 참여자의 Claim을 초기화한다."""
    Team.objects.select_for_update().get(pk=team.pk)
    try:
        participant = Participant.objects.select_for_update().get(pk=participant_id, team=team)
    except Participant.DoesNotExist as error:
        raise ClaimError("선택한 참여자를 찾을 수 없습니다.") from error

    if participant.claimed_by_id is None:
        raise ClaimError("아직 확인되지 않은 참여자입니다.")

    participant.claimed_by = None
    participant.save(update_fields=["claimed_by"])


@transaction.atomic
def end_team_and_retain_chat(*, team):
    """게임을 종료하고 채팅 데이터는 종료 후 7일간 보관한다."""
    locked_team = Team.objects.select_for_update().get(pk=team.pk)
    if locked_team.status == Team.Status.ENDED:
        raise AdminAccessError("이미 종료된 팀입니다.")

    generate_leaderboard_snapshot(locked_team)
    locked_team.status = Team.Status.ENDED
    locked_team.ended_at = timezone.now()
    locked_team.save(update_fields=["status", "ended_at", "updated_at"])
    publish_user_events_on_commit(
        Participant.objects.filter(team=locked_team, claimed_by__isnull=False).values_list("claimed_by_id", flat=True),
        "chat.rooms.changed",
    )
    return locked_team
