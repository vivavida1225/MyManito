from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("teams", "0011_scoreevent_quiz_item_scoreevent_reason_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="low_score_reveal_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="team",
            name="low_score_reveal_interval_days",
            field=models.PositiveSmallIntegerField(default=7, validators=[MinValueValidator(1)]),
        ),
        migrations.AddField(
            model_name="team",
            name="low_score_reveal_next_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="team",
            name="low_score_reveal_percentage",
            field=models.PositiveSmallIntegerField(
                default=30,
                validators=[MinValueValidator(1), MaxValueValidator(30)],
            ),
        ),
        migrations.AddField(
            model_name="team",
            name="low_score_reveal_timezone",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
