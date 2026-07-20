from django.contrib import admin

from .models import Message, MessageAttachment


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "team", "sender", "recipient", "created_at", "read_at")
    search_fields = ("team__code", "content")
    list_filter = ("team",)


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "created_at", "deleted_at")
