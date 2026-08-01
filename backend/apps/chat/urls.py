from django.urls import path

from .views import (
    ChatLikeView,
    ChatMessageView,
    ChatProfileView,
    ChatRoomReadView,
    ChatRoomListView,
    FeedbackMessageView,
    FeedbackThreadReadView,
    FeedbackThreadCreateView,
)


urlpatterns = [
    path("rooms/", ChatRoomListView.as_view(), name="chat-room-list"),
    path("feedback/", FeedbackThreadCreateView.as_view(), name="feedback-thread-create"),
    path("feedback/<int:thread_id>/messages/", FeedbackMessageView.as_view(), name="feedback-messages"),
    path("feedback/<int:thread_id>/read/", FeedbackThreadReadView.as_view(), name="feedback-thread-read"),
    path("<str:room_id>/messages/", ChatMessageView.as_view(), name="chat-messages"),
    path("<str:room_id>/read/", ChatRoomReadView.as_view(), name="chat-room-read"),
    path("<str:room_id>/profile/", ChatProfileView.as_view(), name="chat-profile"),
    path("<str:room_id>/like/", ChatLikeView.as_view(), name="chat-like"),
]
