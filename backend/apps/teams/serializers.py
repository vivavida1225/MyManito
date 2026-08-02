import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from .models import Team


NAME_SEPARATOR_PATTERN = re.compile(r"[,\s]+")


def validate_planned_end_fields(attrs):
    planned_end_date = attrs.get("planned_end_date")
    planned_end_timezone = attrs.get("planned_end_timezone", "")

    if planned_end_date is None:
        if planned_end_timezone:
            raise serializers.ValidationError(
                {"planned_end_timezone": "종료 예정일이 있을 때만 시간대를 설정할 수 있습니다."}
            )
        return

    if not planned_end_timezone:
        raise serializers.ValidationError(
            {"planned_end_timezone": "관리자 지역 시간대를 입력해 주세요."}
        )
    try:
        ZoneInfo(planned_end_timezone)
    except ZoneInfoNotFoundError as error:
        raise serializers.ValidationError(
            {"planned_end_timezone": "올바르지 않은 시간대입니다."}
        ) from error


def parse_participant_names(raw_names):
    """콤마·공백·줄바꿈으로 구분된 명단을 순서가 있는 이름 목록으로 변환한다."""
    names = [name.strip() for name in NAME_SEPARATOR_PATTERN.split(raw_names) if name.strip()]

    if len(names) < 2:
        raise serializers.ValidationError("참여자는 최소 2명 이상이어야 합니다.")

    overlong_names = [name for name in names if len(name) > 100]
    if overlong_names:
        raise serializers.ValidationError("참여자 이름은 100자 이하여야 합니다.")

    if len(set(names)) != len(names):
        raise serializers.ValidationError("동명이인은 구분 가능한 이름으로 입력해 주세요.")

    return names


class TeamCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=100, trim_whitespace=True)
    rules = serializers.CharField(required=False, allow_blank=True, default="")
    reciprocal_ratio = serializers.IntegerField(
        required=False,
        default=20,
        min_value=0,
        max_value=100,
    )
    is_participating = serializers.BooleanField()
    participant_names = serializers.CharField(max_length=10000, trim_whitespace=False)
    reveal_mode = serializers.ChoiceField(
        choices=Team.RevealMode.choices,
        required=False,
        default=Team.RevealMode.AUTO,
    )
    planned_end_date = serializers.DateField(required=False, allow_null=True)
    planned_end_timezone = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate_code(self, value):
        if not value:
            raise serializers.ValidationError("팀 코드를 입력해 주세요.")
        if any(character.isspace() for character in value):
            raise serializers.ValidationError("팀 코드에는 공백을 사용할 수 없습니다.")
        if Team.objects.filter(code=value).exists():
            raise serializers.ValidationError("이미 사용 중인 팀 코드입니다.")
        return value

    def validate(self, attrs):
        validate_planned_end_fields(attrs)
        names = parse_participant_names(attrs["participant_names"])
        user_nickname = self.context["request"].user.kakao_nickname

        if not user_nickname:
            raise serializers.ValidationError("카카오 닉네임을 확인할 수 없습니다. 다시 로그인해 주세요.")

        if attrs["is_participating"] and user_nickname not in names:
            raise serializers.ValidationError(
                {"participant_names": "관리자 참여 시 카카오 닉네임을 명단에 포함해야 합니다."}
            )

        if not attrs["is_participating"] and user_nickname in names:
            raise serializers.ValidationError(
                {"participant_names": "관리자가 미참여라면 본인 닉네임을 명단에서 제외해야 합니다."}
            )

        if len(names) == 2 and attrs["reciprocal_ratio"] < 100:
            raise serializers.ValidationError(
                {"reciprocal_ratio": "2명 팀은 상호 지목 비율을 100%로 설정해야 합니다."}
            )

        attrs["parsed_participant_names"] = names
        return attrs


class ParticipantClaimSerializer(serializers.Serializer):
    participant_id = serializers.IntegerField(min_value=1)


class ClaimResetSerializer(serializers.Serializer):
    participant_id = serializers.IntegerField(min_value=1)


class TeamEndSerializer(serializers.Serializer):
    confirmation_code = serializers.CharField(max_length=100, trim_whitespace=False)


class TeamDeleteSerializer(serializers.Serializer):
    confirmation_code = serializers.CharField(max_length=100, trim_whitespace=False)


class TeamPlannedEndSerializer(serializers.Serializer):
    planned_end_date = serializers.DateField(required=True)
    planned_end_timezone = serializers.CharField(max_length=64, required=True)
    confirm_quiz_collision = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        validate_planned_end_fields(
            {
                "planned_end_date": attrs.get("planned_end_date"),
                "planned_end_timezone": attrs.get("planned_end_timezone", ""),
            }
        )
        return attrs


class TeamRevealModeSerializer(serializers.Serializer):
    reveal_mode = serializers.ChoiceField(choices=Team.RevealMode.values)


class TeamLowScoreRevealSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    interval_days = serializers.IntegerField(min_value=1)
    percentage = serializers.IntegerField(min_value=1, max_value=50)
    timezone = serializers.CharField(max_length=64)

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise serializers.ValidationError("올바르지 않은 시간대입니다.") from error
        return value


class TeamRulesSerializer(serializers.Serializer):
    rules = serializers.CharField(allow_blank=True, max_length=10000, trim_whitespace=False)


class TeamAnnouncementSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate_message(self, value):
        if not value:
            raise serializers.ValidationError("알림 내용을 입력해 주세요.")
        return value
