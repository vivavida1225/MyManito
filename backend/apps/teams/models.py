from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class Team(models.Model):
    """하나의 마니또 행사와 관리자 설정."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "작성 중"
        ACTIVE = "ACTIVE", "진행 중"
        ENDED = "ENDED", "종료됨"

    class RevealMode(models.TextChoices):
        AUTO = "AUTO", "자동 공개"
        ADMIN = "ADMIN", "관리자 외부 공개"

    class RevealStatus(models.TextChoices):
        AUTO_RELEASED = "AUTO_RELEASED", "자동 공개됨"
        MANUAL_PENDING = "MANUAL_PENDING", "관리자 공개 대기"
        MANUAL_RELEASED = "MANUAL_RELEASED", "관리자 공개 완료"

    code = models.CharField(max_length=100, unique=True, db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_teams",
    )
    rules = models.TextField(blank=True)
    reciprocal_ratio = models.PositiveSmallIntegerField(
        default=20,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    reveal_mode = models.CharField(
        max_length=10,
        choices=RevealMode.choices,
        default=RevealMode.AUTO,
    )
    reveal_status = models.CharField(
        max_length=20,
        choices=RevealStatus.choices,
        default=RevealStatus.AUTO_RELEASED,
    )
    planned_end_date = models.DateField(null=True, blank=True)
    planned_end_timezone = models.CharField(max_length=64, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.code


class Participant(models.Model):
    """팀에 등록된 참여자와 마니또 배정 결과."""

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="participants")
    display_name = models.CharField(max_length=100)
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="claimed_participations",
    )
    anonymous_nickname = models.CharField(max_length=50, blank=True)
    assigned_to = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_from",
    )
    assignment_viewed_at = models.DateTimeField(null=True, blank=True)
    leaderboard_nickname = models.CharField(max_length=100, blank=True)
    leaderboard_avatar_key = models.CharField(max_length=30, blank=True)
    leaderboard_score = models.PositiveIntegerField(default=0)
    last_service_access_score_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team", "display_name"],
                name="unique_participant_name_per_team",
            ),
            models.UniqueConstraint(
                fields=["team", "claimed_by"],
                condition=Q(claimed_by__isnull=False),
                name="one_claimed_participant_per_user_per_team",
            ),
        ]

    def __str__(self):
        return f"{self.team.code} - {self.display_name}"


class ScoreEvent(models.Model):
    """리더보드 점수의 서버 측 검증 이력."""

    class Type(models.TextChoices):
        CHAT_MESSAGE = "CHAT_MESSAGE", "채팅 전송"
        CHAT_LIKE = "CHAT_LIKE", "좋아요"
        TEAM_VISIT = "TEAM_VISIT", "팀 접속 (이전 정책)"
        SERVICE_ACCESS = "SERVICE_ACCESS", "서비스 접속"
        QUIZ_SOLVER_RESULT = "QUIZ_SOLVER_RESULT", "퀴즈 풀이 결과"
        QUIZ_AUTHOR_ADJUSTMENT = "QUIZ_AUTHOR_ADJUSTMENT", "퀴즈 작성자 보상·감점"

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="score_events")
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="score_events")
    event_type = models.CharField(max_length=30, choices=Type.choices)
    room_id = models.CharField(max_length=50, blank=True)
    source_message = models.OneToOneField(
        "chat.Message",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="score_event",
    )
    quiz_item = models.ForeignKey(
        "quizzes.QuizItem",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="score_events",
    )
    points = models.IntegerField()
    requested_points = models.IntegerField(null=True, blank=True)
    reason = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["quiz_item", "event_type"],
                condition=Q(quiz_item__isnull=False),
                name="unique_quiz_score_event_role",
            )
        ]


class LeaderboardSnapshot(models.Model):
    """팀별로 사용자에게 공개되는 최신 순위 스냅샷."""

    team = models.OneToOneField(Team, on_delete=models.CASCADE, related_name="leaderboard_snapshot")
    rankings = models.JSONField(default=list)
    generated_at = models.DateTimeField()
