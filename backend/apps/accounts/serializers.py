from rest_framework import serializers


class KakaoAuthorizationCodeSerializer(serializers.Serializer):
    authorization_code = serializers.CharField(max_length=2048, trim_whitespace=True)
