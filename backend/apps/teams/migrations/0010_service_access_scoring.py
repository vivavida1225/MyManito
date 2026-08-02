from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("teams", "0009_sync_anonymous_nickname_with_leaderboard")]

    operations = [
        migrations.RenameField(
            model_name="participant",
            old_name="last_visit_score_at",
            new_name="last_service_access_score_at",
        ),
        migrations.AlterField(
            model_name="scoreevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("CHAT_MESSAGE", "채팅 전송"),
                    ("CHAT_LIKE", "좋아요"),
                    ("TEAM_VISIT", "팀 접속 (이전 정책)"),
                    ("SERVICE_ACCESS", "서비스 접속"),
                ],
                max_length=20,
            ),
        ),
    ]
