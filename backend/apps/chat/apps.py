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

        from .scheduler import cleanup_expired_attachments, cleanup_expired_ended_teams

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
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown(wait=False) if scheduler.running else None)
