from rest_framework import serializers

from .models import Message
from .services import get_anonymous_nickname


EMOTICON_KEYS = (
    *(f"mani-{index}" for index in range(9)),
    *(f"clodi-{index}" for index in range(9)),
    "mani-celebrating",
    "mani-introducing-only",
    "mani-messaging",
    "mani-running-card",
    "mani-thinking",
    "mani-waiting",
)


class MessageListQuerySerializer(serializers.Serializer):
    since = serializers.DateTimeField(required=False)


class MessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    image = serializers.ImageField(required=False)
    emoticon_key = serializers.ChoiceField(choices=EMOTICON_KEYS, required=False)

    def validate(self, attrs):
        if not attrs.get("content") and not attrs.get("image") and not attrs.get("emoticon_key"):
            raise serializers.ValidationError("텍스트, 이미지 또는 이모티콘 중 하나를 입력해 주세요.")
        if attrs.get("image") and attrs.get("emoticon_key"):
            raise serializers.ValidationError("이미지와 이모티콘은 함께 전송할 수 없습니다.")
        return attrs


class ChatProfileUpdateSerializer(serializers.Serializer):
    nickname = serializers.CharField(max_length=50, required=False, allow_blank=False, trim_whitespace=True)
    image = serializers.ImageField(required=False)
    avatar_key = serializers.CharField(max_length=30, required=False, allow_blank=False)
    clear_image = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("수정할 프로필 정보를 입력해 주세요.")
        return attrs


class MessageSerializer(serializers.ModelSerializer):
    is_mine = serializers.SerializerMethodField()
    sender_nickname = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "content",
            "emoticon_key",
            "created_at",
            "read_at",
            "is_mine",
            "sender_nickname",
            "image_url",
        ]

    def get_is_mine(self, obj):
        return obj.sender_id == self.context["participant"].id

    def get_sender_nickname(self, obj):
        if self.get_is_mine(obj):
            return "나"
        return self.context.get("counterpart_nickname") or get_anonymous_nickname(obj.sender)

    def get_image_url(self, obj):
        attachment = next(iter(obj.attachments.all()), None)
        return attachment.image.url if attachment else None
