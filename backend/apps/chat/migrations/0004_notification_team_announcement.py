from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0003_message_emoticon_key"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("MESSAGE", "새 메시지"),
                    ("COUNTERPART_CLAIMED", "상대방 확인 완료"),
                    ("PARTICIPANT_CLAIMED", "참여자 확인 완료"),
                    ("DDAY", "D-Day"),
                    ("RESULT_AVAILABLE", "결과 공개"),
                    ("TEAM_ANNOUNCEMENT", "팀 공지"),
                ],
                max_length=30,
            ),
        ),
    ]
