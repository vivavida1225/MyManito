from django.contrib import admin

from .models import FeedbackMessage, FeedbackThread, Message, MessageAttachment


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "team", "sender", "recipient", "created_at", "read_at")
    search_fields = ("team__code", "content")
    list_filter = ("team",)


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "created_at", "deleted_at")


@admin.register(FeedbackThread)
class FeedbackThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "developer", "updated_at")
    search_fields = ("user__username", "user__kakao_nickname")


@admin.register(FeedbackMessage)
class FeedbackMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "thread", "sender", "created_at", "read_at")
    search_fields = ("content",)
