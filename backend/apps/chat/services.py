import json
import logging
import re
import threading
from dataclasses import dataclass
from datetime import timedelta

import requests
from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.push import send_web_push, send_web_push_async
from apps.accounts.models import User
from apps.accounts.services import KakaoAPIError, refresh_kakao_access_token
from apps.realtime.events import publish_user_events_on_commit
from apps.teams.models import Participant, Team

from .models import ChatProfile, FeedbackMessage, FeedbackMessageAttachment, FeedbackThread, Message, MessageAttachment, Notification


logger = logging.getLogger(__name__)
KAKAO_MEMO_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
ROOM_ID_PATTERN = re.compile(r"^(?P<first>\d+)-(?P<second>\d+)$")
DEFAULT_ANONYMOUS_NICKNAMES = ("마니", "클로디", "마이마니", "마이클로디")
CHAT_RETENTION_DAYS = 7
DEVELOPER_USER_ID = 1


class ChatRoomError(Exception):
    """요청한 채팅방에 접근하거나 전송할 수 없을 때 발생한다."""


class FeedbackError(Exception):
    """개발자 피드백 대화방에 접근할 수 없을 때 발생한다."""


@dataclass(frozen=True)
class ChatRoom:
    team: Team
    me: Participant
    counterpart: Participant

    @property
    def room_id(self):
        return make_room_id(self.me.id, self.counterpart.id)


def make_room_id(first_participant_id, second_participant_id):
    first, second = sorted([first_participant_id, second_participant_id])
    return f"{first}-{second}"


def get_or_create_feedback_thread(user):
    try:
        developer = User.objects.get(pk=DEVELOPER_USER_ID)
    except User.DoesNotExist as error:
        raise FeedbackError("개발자 계정을 찾을 수 없습니다.") from error
    if user.id == developer.id:
        raise FeedbackError("개발자 계정에서는 피드백 대화방을 만들 수 없습니다.")
    thread, _ = FeedbackThread.objects.get_or_create(user=user, developer=developer)
    return thread


def get_feedback_thread_for_user(*, thread_id, user):
    try:
        thread = FeedbackThread.objects.select_related("user", "developer").get(pk=thread_id)
    except FeedbackThread.DoesNotExist as error:
        raise FeedbackError("피드백 대화방을 찾을 수 없습니다.") from error
    if user.id not in {thread.user_id, thread.developer_id}:
        raise FeedbackError("이 피드백 대화방에 접근할 권한이 없습니다.")
    return thread


@transaction.atomic
def create_feedback_message(
    *,
    thread,
    sender,
    content,
    image=None,
    emoticon_key="",
    client_temp_id=None,
):
    """개발자 피드백 메시지를 저장하고 커밋 후 실시간 이벤트를 발행한다."""
    recipient_id = thread.developer_id if sender.id == thread.user_id else thread.user_id
    message = FeedbackMessage.objects.create(
        thread=thread,
        sender=sender,
        content=content,
        emoticon_key=emoticon_key,
    )
    if image:
        FeedbackMessageAttachment.objects.create(message=message, image=image)
    FeedbackThread.objects.filter(pk=thread.pk).update(updated_at=message.created_at)
    Notification.objects.create(
        recipient_id=recipient_id,
        feedback_message=message,
        kind=Notification.Kind.FEEDBACK_MESSAGE,
        title="새 개발자 피드백",
        body="새 메시지가 도착했습니다.",
        data={"feedback_thread_id": thread.id},
    )
    transaction.on_commit(
        lambda: send_web_push_async(
            user_id=recipient_id,
            title="새 개발자 피드백",
            body="새 메시지가 도착했습니다.",
            path=f"/feedback/{thread.id}",
        )
    )

    if client_temp_id:
        sender_payload = _realtime_message_payload(
            message,
            is_mine=True,
            sender_nickname="나",
        )
        recipient_nickname = (
            thread.user.kakao_nickname or thread.user.username
            if recipient_id == thread.developer_id
            else "개발자"
        )
        recipient_payload = _realtime_message_payload(
            message,
            is_mine=False,
            sender_nickname=recipient_nickname,
        )
        publish_user_events_on_commit(
            [sender.id],
            "chat.message.created",
            feedback_thread_id=thread.id,
            tempId=client_temp_id,
            message=sender_payload,
        )
        publish_user_events_on_commit(
            [recipient_id],
            "chat.message.created",
            feedback_thread_id=thread.id,
            tempId=client_temp_id,
            message=recipient_payload,
        )
    else:
        publish_user_events_on_commit(
            [sender.id, recipient_id],
            "chat.message.created",
            feedback_thread_id=thread.id,
        )
    publish_user_events_on_commit([sender.id, recipient_id], "chat.rooms.changed")
    publish_user_events_on_commit([recipient_id], "notifications.changed")
    return message


def list_feedback_threads(user):
    if user.id != DEVELOPER_USER_ID:
        return []

    threads = FeedbackThread.objects.select_related("user", "developer")
    threads = threads.filter(developer_id=user.id)

    rooms = []
    for thread in threads:
        latest_message = thread.messages.order_by("-created_at", "-id").first()
        is_developer = user.id == thread.developer_id
        if latest_message and latest_message.content:
            latest_message_preview = latest_message.content
        elif latest_message and latest_message.emoticon_key:
            latest_message_preview = "이모티콘을 보냈어요."
        elif latest_message and FeedbackMessageAttachment.objects.filter(message=latest_message).exists():
            latest_message_preview = "사진을 보냈어요."
        else:
            latest_message_preview = "개발자에게 의견을 남겨 보세요."
        rooms.append(
            {
                "thread_id": thread.id,
                "title": f"{thread.user.kakao_nickname or thread.user.username} 님의 피드백" if is_developer else "개발자에게 피드백",
                "latest_message_preview": latest_message_preview,
                "latest_message_at": latest_message.created_at if latest_message else thread.created_at,
                "unread_count": FeedbackMessage.objects.filter(thread=thread, read_at__isnull=True).exclude(sender=user).count(),
            }
        )
    return rooms


def get_default_anonymous_nickname(participant):
    """참여자별로 일관되게 표시할 기본 익명 닉네임을 반환한다."""
    return DEFAULT_ANONYMOUS_NICKNAMES[(participant.id - 1) % len(DEFAULT_ANONYMOUS_NICKNAMES)]


def get_anonymous_nickname(participant):
    return participant.anonymous_nickname or get_default_anonymous_nickname(participant)


def is_chat_available(team):
    if team.status == Team.Status.ACTIVE:
        return True
    return (
        team.status == Team.Status.ENDED
        and team.ended_at is not None
        and team.ended_at + timedelta(days=CHAT_RETENTION_DAYS) > timezone.now()
    )


def get_chat_room_for_user(*, room_id, user):
    """room_id를 해석하고 현재 사용자가 속한 인접 마니또 방인지 확인한다."""
    match = ROOM_ID_PATTERN.fullmatch(room_id)
    if not match:
        raise ChatRoomError("올바르지 않은 채팅방입니다.")

    first_id = int(match.group("first"))
    second_id = int(match.group("second"))
    if first_id == second_id:
        raise ChatRoomError("올바르지 않은 채팅방입니다.")

    participants = Participant.objects.select_related("team", "claimed_by", "assigned_to").in_bulk(
        [first_id, second_id]
    )
    if len(participants) != 2:
        raise ChatRoomError("채팅방을 찾을 수 없습니다.")

    first = participants[first_id]
    second = participants[second_id]
    if first.team_id != second.team_id:
        raise ChatRoomError("채팅방을 찾을 수 없습니다.")

    if first.claimed_by_id == user.id:
        me, counterpart = first, second
    elif second.claimed_by_id == user.id:
        me, counterpart = second, first
    else:
        raise ChatRoomError("이 채팅방에 접근할 권한이 없습니다.")

    if me.assigned_to_id != counterpart.id and counterpart.assigned_to_id != me.id:
        raise ChatRoomError("마니또 관계가 아닌 참여자와는 채팅할 수 없습니다.")
    if not is_chat_available(me.team):
        raise ChatRoomError("종료된 채팅방의 7일 보관 기간이 끝났습니다.")

    return ChatRoom(team=me.team, me=me, counterpart=counterpart)


@transaction.atomic
def mark_chat_room_as_read(*, room, user):
    """현재 사용자가 받은 일반 채팅 메시지와 방 알림을 함께 읽음 처리한다."""
    now = timezone.now()
    marked_message_count = Message.objects.filter(
        team=room.team,
        sender=room.counterpart,
        recipient=room.me,
        read_at__isnull=True,
    ).update(read_at=now)
    marked_notification_count = Notification.objects.filter(
        recipient=user,
        kind=Notification.Kind.MESSAGE,
        data__room_id=room.room_id,
        is_read=False,
    ).update(is_read=True, read_at=now)

    if marked_message_count:
        publish_user_events_on_commit([user.id], "chat.rooms.changed")
    if marked_notification_count:
        publish_user_events_on_commit([user.id], "notifications.changed")

    return {
        "marked_message_count": marked_message_count,
        "marked_notification_count": marked_notification_count,
    }


@transaction.atomic
def mark_feedback_thread_as_read(*, thread, user):
    """현재 사용자가 받은 피드백 메시지와 대화방 알림을 함께 읽음 처리한다."""
    now = timezone.now()
    marked_message_count = FeedbackMessage.objects.filter(
        thread=thread,
        read_at__isnull=True,
    ).exclude(sender=user).update(read_at=now)
    marked_notification_count = Notification.objects.filter(
        recipient=user,
        kind=Notification.Kind.FEEDBACK_MESSAGE,
        feedback_message__thread=thread,
        is_read=False,
    ).update(is_read=True, read_at=now)

    if marked_message_count:
        publish_user_events_on_commit([user.id], "chat.rooms.changed")
    if marked_notification_count:
        publish_user_events_on_commit([user.id], "notifications.changed")

    return {
        "marked_message_count": marked_message_count,
        "marked_notification_count": marked_notification_count,
    }


def list_chat_rooms(user):
    """사용자가 Claim한 모든 참여자에서 인접한 마니또 채팅방을 구성한다."""
    my_participants = (
        Participant.objects.filter(claimed_by=user)
        .select_related("team", "assigned_to", "assigned_to__claimed_by")
        .prefetch_related("assigned_from", "assigned_from__claimed_by")
    )
    rooms = {}
    for me in my_participants:
        if not is_chat_available(me.team):
            continue
        are_results_released = (
            me.team.status == Team.Status.ENDED
            and me.team.reveal_status in {
                Team.RevealStatus.AUTO_RELEASED,
                Team.RevealStatus.MANUAL_RELEASED,
            }
        )
        counterparts = []
        if me.assigned_to_id:
            counterparts.append((me.assigned_to, "내가 챙겨줄 사람"))
        counterparts.extend((participant, "나를 챙겨주는 마니또") for participant in me.assigned_from.all())

        for counterpart, relationship_label in counterparts:
            room_id = make_room_id(me.id, counterpart.id)
            if room_id in rooms:
                continue
            profile = ChatProfile.objects.filter(owner=counterpart, counterpart=me).first()
            latest_message = (
                Message.objects.filter(team=me.team)
                .filter(
                    Q(sender=me, recipient=counterpart)
                    | Q(sender=counterpart, recipient=me)
                )
                .order_by("-created_at", "-id")
                .first()
            )
            if latest_message and latest_message.content:
                latest_message_preview = latest_message.content
            elif latest_message and latest_message.emoticon_key:
                latest_message_preview = "이모티콘을 보냈어요."
            elif latest_message and MessageAttachment.objects.filter(message=latest_message).exists():
                latest_message_preview = "사진을 보냈어요."
            else:
                latest_message_preview = "아직 주고받은 메시지가 없어요."
            rooms[room_id] = {
                "room_id": room_id,
                "team_code": me.team.code,
                "relationship_label": relationship_label,
                "counterpart_name": (
                    counterpart.display_name
                    if relationship_label == "내가 챙겨줄 사람" or are_results_released
                    else None
                ),
                "counterpart_claimed": counterpart.claimed_by_id is not None,
                "counterpart_nickname": (
                    profile.nickname if profile and profile.nickname else get_anonymous_nickname(counterpart)
                ),
                "counterpart_profile_image_url": profile.image.url if profile and profile.image else None,
                "counterpart_avatar_key": profile.avatar_key if profile else "default",
                "latest_message_preview": latest_message_preview,
                "latest_message_at": latest_message.created_at if latest_message else None,
                "unread_count": Message.objects.filter(
                    team=me.team,
                    sender=counterpart,
                    recipient=me,
                    read_at__isnull=True,
                ).count(),
            }
    return sorted(
        rooms.values(),
        key=lambda room: (room["latest_message_at"] is not None, room["latest_message_at"]),
        reverse=True,
    )


@transaction.atomic
def create_message(*, room, content, image, emoticon_key="", client_temp_id=None):
    """메시지와 첨부 이미지를 저장한 뒤, 커밋 성공 후 수신자 알림을 예약한다."""
    team = Team.objects.select_for_update().get(pk=room.team.id)
    me = Participant.objects.select_for_update().get(pk=room.me.id)
    counterpart = Participant.objects.select_for_update().get(pk=room.counterpart.id)
    if not is_chat_available(team):
        raise ChatRoomError("종료된 채팅방의 7일 보관 기간이 끝났습니다.")
    if me.claimed_by_id is None or counterpart.claimed_by_id is None:
        raise ChatRoomError("상대방이 아직 본인 확인을 완료하지 않았습니다.")

    message = Message.objects.create(
        team=team,
        sender=me,
        recipient=counterpart,
        content=content,
        emoticon_key=emoticon_key,
    )
    if image:
        MessageAttachment.objects.create(message=message, image=image)

    Notification.objects.create(
        recipient=counterpart.claimed_by,
        team=team,
        message=message,
        kind=Notification.Kind.MESSAGE,
        title="새 익명 마니또 메시지",
        body="새 메시지가 도착했습니다.",
        data={"room_id": room.room_id},
    )

    transaction.on_commit(lambda: notify_message_recipient_async(message.id))
    if client_temp_id:
        publish_user_events_on_commit(
            [me.claimed_by_id],
            "chat.message.created",
            room_id=room.room_id,
            tempId=client_temp_id,
            message=_realtime_message_payload(
                message,
                is_mine=True,
                sender_nickname="나",
            ),
        )
        publish_user_events_on_commit(
            [counterpart.claimed_by_id],
            "chat.message.created",
            room_id=room.room_id,
            tempId=client_temp_id,
            message=_realtime_message_payload(
                message,
                is_mine=False,
                sender_nickname=get_anonymous_nickname(me),
            ),
        )
    else:
        publish_user_events_on_commit(
            [me.claimed_by_id, counterpart.claimed_by_id],
            "chat.message.created",
            room_id=room.room_id,
        )
    publish_user_events_on_commit(
        [me.claimed_by_id, counterpart.claimed_by_id],
        "chat.rooms.changed",
    )
    publish_user_events_on_commit(
        [counterpart.claimed_by_id],
        "notifications.changed",
    )
    from apps.teams.leaderboard_services import award_message_score

    award_message_score(message=message, room_id=room.room_id)
    return message


def _realtime_message_payload(message, *, is_mine, sender_nickname):
    return {
        "id": message.id,
        "content": message.content,
        "emoticon_key": message.emoticon_key,
        "created_at": message.created_at.isoformat(),
        "read_at": message.read_at.isoformat() if message.read_at else None,
        "is_mine": is_mine,
        "sender_nickname": sender_nickname,
        "image_url": None,
    }


def get_or_create_chat_profile(*, owner, counterpart):
    profile, _ = ChatProfile.objects.get_or_create(owner=owner, counterpart=counterpart)
    return profile


def notify_message_recipient(message_id):
    """수신자의 웹 푸시와 카카오 나와의 채팅방에 익명 알림을 보낸다."""
    message = Message.objects.select_related("recipient__claimed_by").filter(pk=message_id).first()
    if not message or not message.recipient.claimed_by_id:
        return False

    room_id = make_room_id(message.sender_id, message.recipient_id)
    send_web_push(
        user_id=message.recipient.claimed_by_id,
        title="새 익명 마니또 메시지",
        body="새 메시지가 도착했습니다.",
        path=f"/chat/{room_id}",
    )
    if (
        not message.recipient.claimed_by.kakao_notification_enabled
        or "talk_message" not in message.recipient.claimed_by.kakao_scopes
    ):
        return False

    chat_url = f"{settings.MYMANITO_APP_URL.rstrip('/')}/chat/{room_id}"
    try:
        access_token = refresh_kakao_access_token(message.recipient.claimed_by)
        response = requests.post(
            KAKAO_MEMO_SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            data={
                "template_object": json.dumps(
                    {
                        "object_type": "text",
                        "text": "익명 마니또로부터 새로운 메시지가 도착했습니다. 앱에서 확인해 보세요!",
                        "link": {
                            "web_url": chat_url,
                            "mobile_web_url": chat_url,
                        },
                        "button_title": "확인하러 가기",
                    }
                )
            },
            timeout=settings.KAKAO_REQUEST_TIMEOUT_SECONDS,
        )
        if not response.ok:
            logger.warning("Kakao memo notification failed: status=%s", response.status_code)
            return False
    except (KakaoAPIError, requests.RequestException) as error:
        logger.warning("Kakao memo notification could not be sent: %s", error)
        return False

    Message.objects.filter(pk=message_id).update(kakao_notified_at=timezone.now())
    return True


def notify_message_recipient_async(message_id):
    """채팅 푸시와 카카오 알림을 요청 응답과 분리해 보낸다."""
    threading.Thread(
        target=_notify_message_recipient_in_background,
        args=(message_id,),
        daemon=True,
        name="mymanito-message-notification",
    ).start()


def _notify_message_recipient_in_background(message_id):
    close_old_connections()
    try:
        notify_message_recipient(message_id)
    except Exception:
        logger.exception("Background message notification failed")
    finally:
        close_old_connections()
