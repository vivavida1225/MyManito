from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.push import send_web_push_async
from apps.realtime.events import publish_user_events_on_commit
from .models import ChatProfile, FeedbackMessage, Notification, Message
from .serializers import (
    ChatProfileUpdateSerializer,
    MessageCreateSerializer,
    MessageListQuerySerializer,
    MessageSerializer,
)
from .services import (
    ChatRoomError,
    FeedbackError,
    create_feedback_message,
    create_message,
    get_feedback_thread_for_user,
    get_chat_room_for_user,
    get_anonymous_nickname,
    get_or_create_chat_profile,
    list_chat_rooms,
    list_feedback_threads,
    mark_chat_room_as_read,
    mark_feedback_thread_as_read,
    get_or_create_feedback_thread,
)
from apps.teams.leaderboard_services import award_like_score


class ChatRoomListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "rooms": list_chat_rooms(request.user),
                "feedback_rooms": list_feedback_threads(request.user),
            }
        )


class FeedbackThreadCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            thread = get_or_create_feedback_thread(request.user)
        except FeedbackError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"thread_id": thread.id}, status=status.HTTP_201_CREATED)


class FeedbackMessageView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request, thread_id):
        try:
            thread = get_feedback_thread_for_user(thread_id=thread_id, user=request.user)
        except FeedbackError as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)

        query_serializer = MessageListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        messages = FeedbackMessage.objects.filter(thread=thread).select_related("sender").prefetch_related("attachments")
        since = query_serializer.validated_data.get("since")
        if since:
            messages = messages.filter(created_at__gt=since)
        messages = list(messages)
        mark_feedback_thread_as_read(thread=thread, user=request.user)
        is_developer = request.user.id == thread.developer_id
        return Response(
            {
                "room": {
                    "title": f"{thread.user.kakao_nickname or thread.user.username} 님의 피드백" if is_developer else "개발자에게 피드백",
                    "subtitle": "개발자와 나눈 대화" if not is_developer else "사용자 피드백 대화",
                    "is_feedback": True,
                },
                "messages": [_feedback_message_payload(message, request.user, thread) for message in messages],
                "next_since": messages[-1].created_at.isoformat() if messages else since,
            }
        )

    def post(self, request, thread_id):
        try:
            thread = get_feedback_thread_for_user(thread_id=thread_id, user=request.user)
        except FeedbackError as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)

        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = create_feedback_message(
            thread=thread,
            sender=request.user,
            content=serializer.validated_data.get("content", ""),
            image=serializer.validated_data.get("image"),
            emoticon_key=serializer.validated_data.get("emoticon_key", ""),
        )
        message = FeedbackMessage.objects.select_related("sender").prefetch_related("attachments").get(pk=message.pk)
        return Response(_feedback_message_payload(message, request.user, thread), status=status.HTTP_201_CREATED)


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

        mark_chat_room_as_read(room=room, user=request.user)

        return Response(
            {
                "room": {
                    "team_code": room.team.code,
                    "team_status": room.team.status,
                    "my_anonymous_nickname": room.me.anonymous_nickname,
                },
                "messages": MessageSerializer(
                    messages,
                    many=True,
                    context=_message_serializer_context(room),
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
                emoticon_key=serializer.validated_data.get("emoticon_key", ""),
            )
        except ChatRoomError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        message = Message.objects.select_related("sender").prefetch_related("attachments").get(pk=message.pk)
        return Response(
            MessageSerializer(message, context=_message_serializer_context(room)).data,
            status=status.HTTP_201_CREATED,
        )


class ChatRoomReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, room_id):
        try:
            room = get_chat_room_for_user(room_id=room_id, user=request.user)
        except ChatRoomError as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)
        return Response(mark_chat_room_as_read(room=room, user=request.user))


class FeedbackThreadReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, thread_id):
        try:
            thread = get_feedback_thread_for_user(thread_id=thread_id, user=request.user)
        except FeedbackError as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)
        return Response(mark_feedback_thread_as_read(thread=thread, user=request.user))


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
                "my_profile": _profile_payload(
                    get_or_create_chat_profile(
                        owner=room.me,
                        counterpart=room.counterpart,
                    ),
                    default_nickname=room.me.leaderboard_nickname,
                ),
                "counterpart_profile": _profile_payload(
                    get_or_create_chat_profile(owner=room.counterpart, counterpart=room.me),
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
        if room.counterpart.claimed_by_id:
            publish_user_events_on_commit(
                [room.counterpart.claimed_by_id],
                "chat.rooms.changed",
            )
        return Response(
            {
                "my_profile": _profile_payload(
                    profile,
                    default_nickname=room.me.leaderboard_nickname,
                )
            }
        )


class ChatLikeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, room_id):
        try:
            room = get_chat_room_for_user(room_id=room_id, user=request.user)
            _awarded, next_available_at = award_like_score(room=room)
        except ChatRoomError as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)
        except PermissionError as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"available": False, "next_available_at": next_available_at})


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _ensure_d_day_notifications(request.user)
        notification_queryset = Notification.objects.filter(recipient=request.user).select_related(
            "team",
            "message",
            "feedback_message",
        )
        unread_count = notification_queryset.filter(is_read=False).count()
        notifications = notification_queryset[:50]
        return Response(
            {
                "unread_count": unread_count,
                "notifications": [
                    {
                        "id": notification.id,
                        "kind": notification.kind,
                        "team_code": notification.team.code if notification.team_id else None,
                        "message_id": notification.message_id,
                        "feedback_message_id": notification.feedback_message_id,
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
            publish_user_events_on_commit([request.user.id], "notifications.changed")
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        marked_count = Notification.objects.filter(recipient=request.user, is_read=False).update(
            is_read=True,
            read_at=timezone.now(),
        )
        if marked_count:
            publish_user_events_on_commit([request.user.id], "notifications.changed")
        return Response({"marked_count": marked_count})


class NotificationClearView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        deleted_count, _ = Notification.objects.filter(recipient=request.user).delete()
        if deleted_count:
            publish_user_events_on_commit([request.user.id], "notifications.changed")
        return Response({"deleted_count": deleted_count})


def _profile_payload(profile, *, default_nickname=None):
    payload = {
        "nickname": profile.nickname,
        "image_url": profile.image.url if profile.image else None,
        "avatar_key": profile.avatar_key,
    }
    if default_nickname is not None:
        payload["default_nickname"] = default_nickname
    return payload


def _message_serializer_context(room):
    profile = ChatProfile.objects.filter(
        owner=room.counterpart,
        counterpart=room.me,
    ).first()
    return {
        "participant": room.me,
        "counterpart_nickname": (
            profile.nickname if profile and profile.nickname else get_anonymous_nickname(room.counterpart)
        ),
    }


def _feedback_message_payload(message, current_user, thread):
    is_mine = message.sender_id == current_user.id
    if is_mine:
        sender_nickname = "나"
    elif current_user.id == thread.user_id:
        sender_nickname = "개발자"
    else:
        sender_nickname = thread.user.kakao_nickname or thread.user.username
    attachment = next(iter(message.attachments.all()), None)
    return {
        "id": message.id,
        "content": message.content,
        "emoticon_key": message.emoticon_key,
        "created_at": message.created_at,
        "read_at": message.read_at,
        "is_mine": is_mine,
        "sender_nickname": sender_nickname,
        "image_url": attachment.image.url if attachment else None,
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
        notification, created = Notification.objects.get_or_create(
            recipient=user,
            team=participant.team,
            kind=Notification.Kind.DDAY,
            defaults={
                "title": "오늘은 D-Day!",
                "body": "마니또 게임 종료 예정일입니다.",
                "data": {"planned_end_date": str(participant.team.planned_end_date)},
            },
        )
        if created:
            transaction.on_commit(
                lambda: send_web_push_async(
                    user_id=user.id,
                    title=notification.title,
                    body=notification.body,
                    path=f"/teams/{participant.team.code}",
                )
            )
            publish_user_events_on_commit([user.id], "notifications.changed")
