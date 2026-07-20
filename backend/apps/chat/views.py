from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification, Message
from .serializers import (
    ChatProfileUpdateSerializer,
    MessageCreateSerializer,
    MessageListQuerySerializer,
    MessageSerializer,
)
from .services import (
    ChatRoomError,
    create_message,
    get_chat_room_for_user,
    get_anonymous_nickname,
    get_or_create_chat_profile,
    list_chat_rooms,
)


class ChatRoomListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"rooms": list_chat_rooms(request.user)})


class ChatMessageView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request, room_id):
        try:
            room = get_chat_room_for_user(room_id=room_id, user=request.user)
        except ChatRoomError as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)

        query_serializer = MessageListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        since = query_serializer.validated_data.get("since")
        messages = Message.objects.filter(
            team=room.team,
            sender__in=[room.me, room.counterpart],
            recipient__in=[room.me, room.counterpart],
        ).select_related("sender").prefetch_related("attachments")
        if since:
            messages = messages.filter(created_at__gt=since)
        messages = list(messages)

        Message.objects.filter(
            team=room.team,
            sender=room.counterpart,
            recipient=room.me,
            read_at__isnull=True,
        ).update(read_at=timezone.now())

        return Response(
            {
                "room": {
                    "team_code": room.team.code,
                    "my_anonymous_nickname": room.me.anonymous_nickname,
                },
                "messages": MessageSerializer(
                    messages,
                    many=True,
                    context={"participant": room.me},
                ).data,
                "next_since": messages[-1].created_at.isoformat() if messages else since,
            }
        )

    def post(self, request, room_id):
        try:
            room = get_chat_room_for_user(room_id=room_id, user=request.user)
        except ChatRoomError as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)

        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            message = create_message(
                room=room,
                content=serializer.validated_data.get("content", ""),
                image=serializer.validated_data.get("image"),
            )
        except ChatRoomError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        message = Message.objects.select_related("sender").prefetch_related("attachments").get(pk=message.pk)
        return Response(
            MessageSerializer(message, context={"participant": room.me}).data,
            status=status.HTTP_201_CREATED,
        )


class ChatProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request, room_id):
        try:
            room = get_chat_room_for_user(room_id=room_id, user=request.user)
        except ChatRoomError as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)

        return Response(
            {
                "team_code": room.team.code,
                "my_profile": _profile_payload(get_or_create_chat_profile(owner=room.me, counterpart=room.counterpart), room.me),
                "counterpart_profile": _profile_payload(
                    get_or_create_chat_profile(owner=room.counterpart, counterpart=room.me),
                    room.counterpart,
                ),
            }
        )

    def patch(self, request, room_id):
        try:
            room = get_chat_room_for_user(room_id=room_id, user=request.user)
        except ChatRoomError as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)

        serializer = ChatProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = get_or_create_chat_profile(owner=room.me, counterpart=room.counterpart)
        if serializer.validated_data.get("clear_image") and profile.image:
            profile.image.delete(save=False)
            profile.image = None
        for field in ("nickname", "image", "avatar_key"):
            if field in serializer.validated_data:
                setattr(profile, field, serializer.validated_data[field])
        profile.save()
        return Response({"my_profile": _profile_payload(profile, room.me)})


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _ensure_d_day_notifications(request.user)
        notification_queryset = Notification.objects.filter(recipient=request.user).select_related("team", "message")
        unread_count = notification_queryset.filter(is_read=False).count()
        notifications = notification_queryset[:50]
        return Response(
            {
                "unread_count": unread_count,
                "notifications": [
                    {
                        "id": notification.id,
                        "kind": notification.kind,
                        "team_code": notification.team.code,
                        "message_id": notification.message_id,
                        "title": notification.title,
                        "body": notification.body,
                        "data": notification.data,
                        "is_read": notification.is_read,
                        "created_at": notification.created_at,
                    }
                    for notification in notifications
                ],
            }
        )


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id):
        try:
            notification = Notification.objects.get(pk=notification_id, recipient=request.user)
        except Notification.DoesNotExist:
            return Response({"detail": "알림을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        marked_count = Notification.objects.filter(recipient=request.user, is_read=False).update(
            is_read=True,
            read_at=timezone.now(),
        )
        return Response({"marked_count": marked_count})


def _profile_payload(profile, participant):
    return {
        "nickname": profile.nickname or get_anonymous_nickname(participant),
        "image_url": profile.image.url if profile.image else None,
        "avatar_key": profile.avatar_key,
    }


def _ensure_d_day_notifications(user):
    from apps.teams.models import Participant, Team
    from apps.teams.services import get_team_countdown

    participants = Participant.objects.filter(claimed_by=user).select_related("team")
    for participant in participants:
        if participant.team.status != Team.Status.ACTIVE:
            continue
        countdown = get_team_countdown(participant.team)
        if countdown["remaining"] != "D-Day!":
            continue
        Notification.objects.get_or_create(
            recipient=user,
            team=participant.team,
            kind=Notification.Kind.DDAY,
            defaults={
                "title": "오늘은 D-Day!",
                "body": "마니또 게임 종료 예정일입니다.",
                "data": {"planned_end_date": str(participant.team.planned_end_date)},
            },
        )
