from datetime import timedelta

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def delete_expired_notifications(apps, schema_editor):
    notification_model = apps.get_model("chat", "Notification")
    cutoff = timezone.now() - timedelta(days=7)
    notification_model.objects.filter(created_at__lte=cutoff).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0006_feedback_message_media"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("MESSAGE", "새 메시지"),
                    ("FEEDBACK_MESSAGE", "새 개발자 피드백"),
                    ("COUNTERPART_CLAIMED", "상대방 확인 완료"),
                    ("PARTICIPANT_CLAIMED", "참여자 확인 완료"),
                    ("DDAY", "D-Day"),
                    ("RESULT_AVAILABLE", "결과 공개"),
                    ("TEAM_ANNOUNCEMENT", "팀 공지"),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="team",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications",
                to="teams.team",
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="feedback_message",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications",
                to="chat.feedbackmessage",
            ),
        ),
        migrations.RunPython(delete_expired_notifications, migrations.RunPython.noop),
    ]
