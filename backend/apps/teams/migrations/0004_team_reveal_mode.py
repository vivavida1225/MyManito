from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("teams", "0003_replace_planned_end_at_with_planned_end_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="reveal_mode",
            field=models.CharField(
                choices=[("AUTO", "자동 공개"), ("ADMIN", "관리자 외부 공개")],
                default="AUTO",
                max_length=10,
            ),
        ),
    ]
