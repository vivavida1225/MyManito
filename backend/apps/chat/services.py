import json
import logging
import re
from dataclasses import dataclass

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.services import KakaoAPIError, refresh_kakao_access_token
from apps.teams.models import Participant, Team

from .models import ChatProfile, Message, MessageAttachment, Notification


logger = logging.getLogger(__name__)
KAKAO_MEMO_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
ROOM_ID_PATTERN = re.compile(r"^(?P<first>\d+)-(?P<second>\d+)$")
DEFAULT_ANONYMOUS_NICKNAMES = ("마니", "클로디", "마이마니", "마이클로디")


class ChatRoomError(Exception):
    """요청한 채팅방에 접근하거나 전송할 수 없을 때 발생한다."""


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


def get_default_anonymous_nickname(participant):
    """참여자별로 일관되게 표시할 기본 익명 닉네임을 반환한다."""
    return DEFAULT_ANONYMOUS_NICKNAMES[(participant.id - 1) % len(DEFAULT_ANONYMOUS_NICKNAMES)]


def get_anonymous_nickname(participant):
    return participant.anonymous_nickname or get_default_anonymous_nickname(participant)


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

    return ChatRoom(team=me.team, me=me, counterpart=counterpart)


def list_chat_rooms(user):
    """사용자가 Claim한 모든 참여자에서 인접한 마니또 채팅방을 구성한다."""
    my_participants = (
        Participant.objects.filter(claimed_by=user)
        .select_related("team", "assigned_to", "assigned_to__claimed_by")
        .prefetch_related("assigned_from", "assigned_from__claimed_by")
    )
    rooms = {}
    for me in my_participants:
        counterparts = []
        if me.assigned_to_id:
            counterparts.append((me.assigned_to, "내가 챙겨줄 사람"))
        counterparts.extend((participant, "나를 챙겨주는 마니또") for participant in me.assigned_from.all())

        for counterpart, relationship_label in counterparts:
            room_id = make_room_id(me.id, counterpart.id)
            if room_id in rooms:
                continue
            profile = ChatProfile.objects.filter(owner=counterpart, counterpart=me).first()
            rooms[room_id] = {
                "room_id": room_id,
                "team_code": me.team.code,
                "relationship_label": relationship_label,
                "counterpart_name": (
                    counterpart.display_name
                    if relationship_label == "내가 챙겨줄 사람"
                    else None
                ),
                "counterpart_claimed": counterpart.claimed_by_id is not None,
                "counterpart_nickname": (
                    profile.nickname if profile and profile.nickname else get_anonymous_nickname(counterpart)
                ),
                "counterpart_profile_image_url": profile.image.url if profile and profile.image else None,
                "counterpart_avatar_key": profile.avatar_key if profile else "default",
                "unread_count": Message.objects.filter(
                    team=me.team,
                    sender=counterpart,
                    recipient=me,
                    read_at__isnull=True,
                ).count(),
            }
    return list(rooms.values())


@transaction.atomic
def create_message(*, room, content, image):
    """메시지와 첨부 이미지를 저장한 뒤, 커밋 성공 후 수신자 알림을 예약한다."""
    team = Team.objects.select_for_update().get(pk=room.team.id)
    me = Participant.objects.select_for_update().get(pk=room.me.id)
    counterpart = Participant.objects.select_for_update().get(pk=room.counterpart.id)
    if team.status != Team.Status.ACTIVE:
        raise ChatRoomError("종료되었거나 비활성화된 팀에서는 메시지를 보낼 수 없습니다.")
    if me.claimed_by_id is None or counterpart.claimed_by_id is None:
        raise ChatRoomError("상대방이 아직 본인 확인을 완료하지 않았습니다.")

    message = Message.objects.create(
        team=team,
        sender=me,
        recipient=counterpart,
        content=content,
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

    transaction.on_commit(lambda: notify_message_recipient(message.id))
    return message


def get_or_create_chat_profile(*, owner, counterpart):
    profile, _ = ChatProfile.objects.get_or_create(owner=owner, counterpart=counterpart)
    return profile


def notify_message_recipient(message_id):
    """수신자의 나와의 채팅방에 발신자 정보를 숨긴 알림을 보낸다."""
    message = Message.objects.select_related("recipient__claimed_by").filter(pk=message_id).first()
    if not message or not message.recipient.claimed_by_id:
        return False

    chat_url = f"{settings.MYMANITO_APP_URL.rstrip('/')}/chat/{make_room_id(message.sender_id, message.recipient_id)}"
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
