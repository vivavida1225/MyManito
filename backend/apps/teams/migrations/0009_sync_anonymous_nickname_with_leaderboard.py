from django.db import migrations
from django.db.models import F


def sync_anonymous_nicknames(apps, schema_editor):
    Participant = apps.get_model("teams", "Participant")
    Participant.objects.exclude(leaderboard_nickname="").update(
        anonymous_nickname=F("leaderboard_nickname"),
    )


class Migration(migrations.Migration):
    dependencies = [("teams", "0008_reassign_leaderboard_profiles_by_character")]

    operations = [
        migrations.RunPython(sync_anonymous_nicknames, migrations.RunPython.noop),
    ]
