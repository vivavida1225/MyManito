from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0008_notification_dedupe_key_alter_notification_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="body",
            field=models.TextField(blank=True),
        ),
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
                    ("LOW_SCORE_REVEAL", "하위 활동 참여자 공개"),
                    ("QUIZ_READY", "퀴즈 활성화 가능"),
                    ("QUIZ_REFERENCE_OPEN", "기준 답안 입력"),
                    ("QUIZ_SOLVE_OPEN", "퀴즈 풀이"),
                    ("QUIZ_EVALUATION_OPEN", "퀴즈 평가"),
                    ("QUIZ_END_CONFLICT", "종료 예정일 충돌"),
                    ("QUIZ_POOL_EXHAUSTED", "질문 풀 소진"),
                    ("QUIZ_ROUND_CANCELLED", "퀴즈 회차 취소"),
                ],
                max_length=30,
            ),
        ),
    ]
