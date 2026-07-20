from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0001_initial"),
        ("teams", "0005_team_reveal_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nickname", models.CharField(blank=True, max_length=50)),
                ("image", models.ImageField(blank=True, upload_to="chat_profiles/%Y/%m/%d/")),
                ("avatar_key", models.CharField(default="default", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("counterpart", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="counterpart_profiles", to="teams.participant")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chat_profiles", to="teams.participant")),
            ],
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("MESSAGE", "새 메시지"), ("COUNTERPART_CLAIMED", "상대방 확인 완료"), ("PARTICIPANT_CLAIMED", "참여자 확인 완료"), ("DDAY", "D-Day"), ("RESULT_AVAILABLE", "결과 공개")], max_length=30)),
                ("title", models.CharField(max_length=100)),
                ("body", models.CharField(blank=True, max_length=255)),
                ("data", models.JSONField(blank=True, default=dict)),
                ("is_read", models.BooleanField(default=False)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("message", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notifications", to="chat.message")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="teams.team")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="chatprofile",
            constraint=models.UniqueConstraint(fields=("owner", "counterpart"), name="unique_chat_profile_per_direction"),
        ),
    ]
