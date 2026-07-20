from django.contrib import admin

from .models import Participant, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("code", "owner", "status", "reciprocal_ratio", "created_at")
    search_fields = ("code", "owner__username")
    list_filter = ("status",)


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ("display_name", "team", "claimed_by", "assigned_to")
    search_fields = ("display_name", "team__code")
    list_filter = ("team",)
