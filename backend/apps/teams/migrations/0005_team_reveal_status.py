from django.db import migrations, models


def initialize_manual_reveal_status(apps, schema_editor):
    Team = apps.get_model("teams", "Team")
    Team.objects.filter(reveal_mode="ADMIN").update(reveal_status="MANUAL_PENDING")


class Migration(migrations.Migration):
    dependencies = [
        ("teams", "0004_team_reveal_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="reveal_status",
            field=models.CharField(
                choices=[
                    ("AUTO_RELEASED", "자동 공개됨"),
                    ("MANUAL_PENDING", "관리자 공개 대기"),
                    ("MANUAL_RELEASED", "관리자 공개 완료"),
                ],
                default="AUTO_RELEASED",
                max_length=20,
            ),
        ),
        migrations.RunPython(initialize_manual_reveal_status, migrations.RunPython.noop),
    ]
