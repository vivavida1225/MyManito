from django.urls import path

from .views import ChatLikeView, ChatMessageView, ChatProfileView, ChatRoomListView


urlpatterns = [
    path("rooms/", ChatRoomListView.as_view(), name="chat-room-list"),
    path("<str:room_id>/messages/", ChatMessageView.as_view(), name="chat-messages"),
    path("<str:room_id>/profile/", ChatProfileView.as_view(), name="chat-profile"),
    path("<str:room_id>/like/", ChatLikeView.as_view(), name="chat-like"),
]
