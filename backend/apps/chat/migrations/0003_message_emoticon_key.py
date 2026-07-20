from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0002_chatprofile_notification"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="emoticon_key",
            field=models.CharField(blank=True, max_length=40),
        ),
    ]
