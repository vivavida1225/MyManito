import atexit
import os
import sys

from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.apps import AppConfig


scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)


class ChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chat"

    def ready(self):
        if not settings.SCHEDULER_ENABLED or "test" in sys.argv:
            return
        if "runserver" in sys.argv and settings.DEBUG and os.environ.get("RUN_MAIN") != "true":
            return
        if scheduler.running:
            return

        from .scheduler import (
            cleanup_expired_attachments,
            cleanup_expired_ended_teams,
            cleanup_expired_notifications,
        )
        from apps.teams.leaderboard_config import LEADERBOARD_SNAPSHOT_INTERVAL_HOURS
        from apps.teams.leaderboard_services import generate_active_leaderboard_snapshots

        scheduler.add_job(
            cleanup_expired_attachments,
            trigger="cron",
            minute=0,
            id="cleanup-expired-chat-attachments",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.add_job(
            cleanup_expired_ended_teams,
            trigger="cron",
            minute=0,
            id="cleanup-expired-ended-teams",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.add_job(
            cleanup_expired_notifications,
            trigger="cron",
            minute=0,
            id="cleanup-expired-notifications",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.add_job(
            generate_active_leaderboard_snapshots,
            trigger="cron",
            hour=f"*/{LEADERBOARD_SNAPSHOT_INTERVAL_HOURS}",
            minute=0,
            id="generate-active-leaderboard-snapshots",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown(wait=False) if scheduler.running else None)
