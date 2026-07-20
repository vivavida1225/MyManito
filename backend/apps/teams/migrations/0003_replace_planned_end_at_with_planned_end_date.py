from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def copy_planned_end_dates(apps, schema_editor):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    Team = apps.get_model("teams", "Team")
    for team in Team.objects.exclude(planned_end_at__isnull=True).iterator():
        try:
            end_timezone = ZoneInfo(team.planned_end_timezone or settings.TIME_ZONE)
        except ZoneInfoNotFoundError:
            end_timezone = timezone.get_current_timezone()

        planned_end_at = team.planned_end_at
        if timezone.is_aware(planned_end_at):
            planned_end_at = timezone.localtime(planned_end_at, end_timezone)
        team.planned_end_date = planned_end_at.date()
        team.save(update_fields=["planned_end_date"])


class Migration(migrations.Migration):
    dependencies = [
        ("teams", "0002_team_planned_end_at_team_planned_end_timezone"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="planned_end_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(copy_planned_end_dates, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="team",
            name="planned_end_at",
        ),
    ]
