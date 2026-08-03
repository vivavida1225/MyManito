from rest_framework import serializers

from .models import QuizRound


class QuizSettingsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    rotation_hour = serializers.IntegerField(required=False, min_value=0, max_value=23)
    reference_days = serializers.IntegerField(required=False, min_value=1, max_value=6)
    solve_days = serializers.IntegerField(required=False, min_value=1, max_value=6)
    next_common_question = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
    )

    def validate(self, attrs):
        if "quiz_timezone" in self.initial_data:
            raise serializers.ValidationError(
                {"quiz_timezone": "관리자 시간대는 변경할 수 없습니다."}
            )
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
