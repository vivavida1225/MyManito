from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("teams", "0012_team_low_score_reveal_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="team",
            name="low_score_reveal_percentage",
            field=models.PositiveSmallIntegerField(
                default=30,
                validators=[MinValueValidator(1), MaxValueValidator(50)],
            ),
        ),
    ]
