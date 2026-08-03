from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def populate_blank_quiz_timezones(apps, schema_editor):
    team_quiz_settings = apps.get_model("quizzes", "TeamQuizSettings")
    team_quiz_settings.objects.filter(quiz_timezone="").update(quiz_timezone="Asia/Seoul")


class Migration(migrations.Migration):

    dependencies = [
        ("quizzes", "0003_quizitem_solve_reminder_sent_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="teamquizsettings",
            name="rotation_hour",
            field=models.PositiveSmallIntegerField(
                default=12,
                validators=[MinValueValidator(0), MaxValueValidator(23)],
            ),
        ),
        migrations.RunPython(populate_blank_quiz_timezones, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="teamquizsettings",
            name="quiz_timezone",
            field=models.CharField(default="Asia/Seoul", max_length=64),
        ),
    ]
