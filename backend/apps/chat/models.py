from django.conf import settings
from django.db import models

from apps.teams.models import Participant, Team


class Message(models.Model):
    """마니또 관계로 연결된 두 참여자 사이의 익명 채팅 메시지."""

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="received_messages")
    content = models.TextField(blank=True)
    emoticon_key = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    kakao_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]


class MessageAttachment(models.Model):
    """메시지에 첨부된 이미지. 읽은 뒤 정리하는 작업은 이후 스케줄러가 담당한다."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")
    image = models.ImageField(upload_to="chat/%Y/%m/%d/")
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)


class ChatProfile(models.Model):
    """특정 상대방에게만 보이는 채팅방별 익명 프로필."""

    owner = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="chat_profiles")
    counterpart = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="counterpart_profiles")
    nickname = models.CharField(max_length=50, blank=True)
    image = models.ImageField(upload_to="chat_profiles/%Y/%m/%d/", blank=True)
    avatar_key = models.CharField(max_length=30, default="default")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "counterpart"],
                name="unique_chat_profile_per_direction",
            )
        ]


class FeedbackThread(models.Model):
    """사용자와 개발자(id=1) 사이의 영구 피드백 대화방."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedback_threads")
    developer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_feedback_threads")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "developer"], name="unique_feedback_thread_per_user"),
        ]


class FeedbackMessage(models.Model):
    """팀 종료 후 정리 대상에 포함되지 않는 개발자 피드백 메시지."""

    thread = models.ForeignKey(FeedbackThread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_feedback_messages")
    content = models.TextField(blank=True)
    emoticon_key = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]


class FeedbackMessageAttachment(models.Model):
    """개발자 피드백 메시지에 첨부된 이미지."""

    message = models.ForeignKey(FeedbackMessage, on_delete=models.CASCADE, related_name="attachments")
    image = models.ImageField(upload_to="feedback_chat/%Y/%m/%d/")
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    """앱 내 팀 이벤트 알림."""

    class Kind(models.TextChoices):
        MESSAGE = "MESSAGE", "새 메시지"
        FEEDBACK_MESSAGE = "FEEDBACK_MESSAGE", "새 개발자 피드백"
        COUNTERPART_CLAIMED = "COUNTERPART_CLAIMED", "상대방 확인 완료"
        PARTICIPANT_CLAIMED = "PARTICIPANT_CLAIMED", "참여자 확인 완료"
        DDAY = "DDAY", "D-Day"
        RESULT_AVAILABLE = "RESULT_AVAILABLE", "결과 공개"
        TEAM_ANNOUNCEMENT = "TEAM_ANNOUNCEMENT", "팀 공지"
        QUIZ_READY = "QUIZ_READY", "퀴즈 활성화 가능"
        QUIZ_REFERENCE_OPEN = "QUIZ_REFERENCE_OPEN", "기준 답안 입력"
        QUIZ_SOLVE_OPEN = "QUIZ_SOLVE_OPEN", "퀴즈 풀이"
        QUIZ_EVALUATION_OPEN = "QUIZ_EVALUATION_OPEN", "퀴즈 평가"
        QUIZ_END_CONFLICT = "QUIZ_END_CONFLICT", "종료 예정일 충돌"
        QUIZ_POOL_EXHAUSTED = "QUIZ_POOL_EXHAUSTED", "질문 풀 소진"
        QUIZ_ROUND_CANCELLED = "QUIZ_ROUND_CANCELLED", "퀴즈 회차 취소"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    message = models.ForeignKey(Message, null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications")
    feedback_message = models.ForeignKey(
        FeedbackMessage,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=30, choices=Kind.choices)
    title = models.CharField(max_length=100)
    body = models.CharField(max_length=255, blank=True)
    data = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=180, null=True, blank=True, unique=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
