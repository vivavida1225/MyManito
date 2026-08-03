from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.teams.models import Participant, Team


class SystemQuizQuestion(models.Model):
    stable_id = models.CharField(max_length=30, unique=True)
    original_number = models.PositiveIntegerField(unique=True)
    category = models.CharField(max_length=255)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField()

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.stable_id}: {self.body}"


class TeamQuizSettings(models.Model):
    team = models.OneToOneField(Team, on_delete=models.CASCADE, related_name="quiz_settings")
    enabled = models.BooleanField(default=False)
    quiz_timezone = models.CharField(max_length=64, default=settings.TIME_ZONE)
    rotation_hour = models.PositiveSmallIntegerField(
        default=12,
        validators=[MinValueValidator(0), MaxValueValidator(23)],
    )
    reference_days = models.PositiveSmallIntegerField(default=2)
    solve_days = models.PositiveSmallIntegerField(default=3)
    next_round_starts_at = models.DateTimeField(null=True, blank=True)
    next_common_question = models.TextField(blank=True)
    next_common_question_normalized = models.TextField(blank=True)
    all_claimed_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class QuizRound(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "진행 중"
        SETTLED = "SETTLED", "정산 완료"
        CANCELLED = "CANCELLED", "취소"

    class CollisionDecision(models.TextChoices):
        NOT_REQUIRED = "NOT_REQUIRED", "결정 불필요"
        PENDING = "PENDING", "결정 대기"
        PROCEED = "PROCEED", "진행"
        CANCEL = "CANCEL", "취소"

    class QuestionMode(models.TextChoices):
        SYSTEM = "SYSTEM", "랜덤 퀴즈"
        COMMON = "COMMON", "공통 퀴즈"

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="quiz_rounds")
    sequence = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    collision_decision = models.CharField(
        max_length=20,
        choices=CollisionDecision.choices,
        default=CollisionDecision.NOT_REQUIRED,
    )
    collision_decided_at = models.DateTimeField(null=True, blank=True)
    collision_decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decided_quiz_rounds",
    )
    question_mode = models.CharField(max_length=10, choices=QuestionMode.choices)
    common_question_snapshot = models.TextField(blank=True)
    quiz_timezone = models.CharField(max_length=64)
    reference_days = models.PositiveSmallIntegerField()
    solve_days = models.PositiveSmallIntegerField()
    starts_at = models.DateTimeField()
    reference_ends_at = models.DateTimeField(db_index=True)
    solve_ends_at = models.DateTimeField(db_index=True)
    evaluation_ends_at = models.DateTimeField(db_index=True)
    reference_processed_at = models.DateTimeField(null=True, blank=True)
    solve_processed_at = models.DateTimeField(null=True, blank=True)
    evaluation_processed_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["team_id", "sequence"]
        constraints = [
            models.UniqueConstraint(fields=["team", "sequence"], name="unique_quiz_round_sequence"),
            models.UniqueConstraint(fields=["team", "starts_at"], name="unique_quiz_round_start"),
        ]


class QuizItem(models.Model):
    class QuestionKind(models.TextChoices):
        SYSTEM = "SYSTEM", "랜덤 퀴즈"
        COMMON = "COMMON", "공통 퀴즈"

    class SettlementKind(models.TextChoices):
        REFERENCE_MISSING = "REFERENCE_MISSING", "기준 답안 미입력"
        SOLUTION_MISSING = "SOLUTION_MISSING", "풀이 답안 미제출"
        EVALUATED = "EVALUATED", "정상 평가"
        EVALUATION_MISSING = "EVALUATION_MISSING", "평가 미완료"

    round = models.ForeignKey(QuizRound, on_delete=models.CASCADE, related_name="items")
    author = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="authored_quiz_items")
    solver = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="solved_quiz_items")
    system_question = models.ForeignKey(
        SystemQuizQuestion,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quiz_items",
    )
    question_kind = models.CharField(max_length=10, choices=QuestionKind.choices)
    question_key = models.CharField(max_length=300)
    question_normalized = models.TextField()
    question_snapshot = models.TextField()
    reference_answer = models.TextField(blank=True)
    reference_confirmed_at = models.DateTimeField(null=True, blank=True)
    solution_draft = models.TextField(blank=True)
    solution_draft_saved_at = models.DateTimeField(null=True, blank=True)
    solve_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    solution_submitted = models.TextField(blank=True)
    solution_submitted_at = models.DateTimeField(null=True, blank=True)
    evaluation_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    evaluated_at = models.DateTimeField(null=True, blank=True)
    settlement_kind = models.CharField(max_length=30, choices=SettlementKind.choices, blank=True)
    raw_score = models.PositiveSmallIntegerField(null=True, blank=True)
    rate_max_score = models.PositiveSmallIntegerField(default=0)
    settled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["round_id", "id"]
        constraints = [
            models.UniqueConstraint(fields=["round", "author"], name="unique_quiz_author_per_round"),
            models.UniqueConstraint(fields=["round", "solver"], name="unique_quiz_solver_per_round"),
            models.CheckConstraint(
                condition=Q(evaluation_score__isnull=True) | Q(evaluation_score__gte=1, evaluation_score__lte=5),
                name="quiz_evaluation_score_between_1_and_5",
            ),
        ]
