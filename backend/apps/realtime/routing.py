from django.urls import path

from .consumer import RealtimeConsumer


websocket_urlpatterns = [path("ws/realtime/", RealtimeConsumer.as_asgi())]
