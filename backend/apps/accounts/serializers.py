from rest_framework import serializers


class KakaoAuthorizationCodeSerializer(serializers.Serializer):
    authorization_code = serializers.CharField(max_length=2048, trim_whitespace=True)


class ServiceLogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(max_length=4096, trim_whitespace=True)


class WebPushDeviceSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=4096, trim_whitespace=True)


class NotificationSettingsSerializer(serializers.Serializer):
    notification_platform = serializers.ChoiceField(choices=("ANDROID", "IOS"), required=False)
    kakao_notification_enabled = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("변경할 알림 설정을 선택해 주세요.")
        return attrs


class IOSWebPushSubscriptionSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=2048)
    p256dh = serializers.CharField(max_length=255)
    auth = serializers.CharField(max_length=255)


class IOSWebPushSubscriptionDeleteSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=2048)
