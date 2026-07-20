from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("teams", "0005_team_reveal_status"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="team",
            name="admin_password",
        ),
    ]
