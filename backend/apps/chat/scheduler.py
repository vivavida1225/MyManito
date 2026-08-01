import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.realtime.events import publish_user_events_on_commit

from .models import Message, MessageAttachment, Notification


logger = logging.getLogger(__name__)


def delete_attachment(attachment):
    """스토리지 파일을 먼저 제거한 뒤 첨부 레코드를 영구 삭제한다."""
    try:
        attachment.image.delete(save=False)
    except Exception:
        logger.exception("Failed to delete chat attachment file: attachment_id=%s", attachment.id)
    attachment.delete()


def cleanup_expired_attachments():
    """진행 중인 팀에서 읽은 지 24시간이 지난 메시지 이미지를 정리한다."""
    from apps.teams.models import Team

    cutoff = timezone.now() - timedelta(hours=24)
    attachments = list(
        MessageAttachment.objects.select_related("message").filter(
            message__read_at__lte=cutoff,
            message__team__status=Team.Status.ACTIVE,
        )
    )
    for attachment in attachments:
        delete_attachment(attachment)
    return len(attachments)


def cleanup_expired_ended_teams():
    """종료 후 7일이 지난 팀의 채팅, 이미지, 참여자 정보를 영구 삭제한다."""
    from apps.teams.models import Team

    cutoff = timezone.now() - timedelta(days=7)
    team_ids = list(
        Team.objects.filter(status=Team.Status.ENDED, ended_at__lte=cutoff).values_list("id", flat=True)
    )
    deleted_count = 0

    for team_id in team_ids:
        with transaction.atomic():
            team = (
                Team.objects.select_for_update()
                .filter(pk=team_id, status=Team.Status.ENDED, ended_at__lte=cutoff)
                .first()
            )
            if team is None:
                continue

            purge_team_chat_data(team.id)
            team.delete()
            deleted_count += 1

    return deleted_count


def cleanup_expired_notifications():
    """생성 후 7일이 지난 앱 알림을 읽음 여부와 관계없이 영구 삭제한다."""
    cutoff = timezone.now() - timedelta(days=7)
    expired_notifications = Notification.objects.filter(created_at__lte=cutoff)
    recipient_ids = list(
        expired_notifications.order_by().values_list("recipient_id", flat=True).distinct()
    )
    deleted_count = expired_notifications.count()
    if not deleted_count:
        return 0

    expired_notifications.delete()
    publish_user_events_on_commit(recipient_ids, "notifications.changed")
    return deleted_count


def purge_team_chat_data(team_id):
    """보관 기간이 끝난 팀의 이미지와 모든 채팅 레코드를 영구 파기한다."""
    attachments = list(
        MessageAttachment.objects.select_related("message").filter(message__team_id=team_id)
    )
    for attachment in attachments:
        delete_attachment(attachment)
    deleted_messages, _ = Message.objects.filter(team_id=team_id).delete()
    logger.info("Purged chat data for ended team_id=%s messages=%s", team_id, deleted_messages)
