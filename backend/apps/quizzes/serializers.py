from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from .models import QuizRound


class QuizSettingsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    quiz_timezone = serializers.CharField(max_length=64, required=False, allow_blank=True)
    reference_days = serializers.IntegerField(required=False, min_value=1, max_value=6)
    solve_days = serializers.IntegerField(required=False, min_value=1, max_value=6)
    next_common_question = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
    )

    def validate_quiz_timezone(self, value):
        if not value:
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise serializers.ValidationError("올바른 IANA 시간대를 입력해 주세요.") from error
        return value

    def validate(self, attrs):
        reference_days = attrs.get("reference_days")
        solve_days = attrs.get("solve_days")
        if reference_days is not None and solve_days is not None and reference_days + solve_days > 7:
            raise serializers.ValidationError("입력일수와 풀이일수 합계는 7일 이하여야 합니다.")
        return attrs


class CollisionDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=[QuizRound.CollisionDecision.PROCEED, QuizRound.CollisionDecision.CANCEL]
    )


class ReferenceAnswerSerializer(serializers.Serializer):
    answer = serializers.CharField(trim_whitespace=False, allow_blank=True)


class SolutionDraftSerializer(serializers.Serializer):
    answer = serializers.CharField(trim_whitespace=False, allow_blank=True)


class EvaluationSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=1, max_value=5)

