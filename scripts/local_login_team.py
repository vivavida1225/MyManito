import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.teams.models import Participant, Team


def main():
    database = settings.DATABASES["default"]
    if not settings.DEBUG:
        raise SystemExit("Refusing local login because DEBUG is disabled.")
    if settings.OUTBOUND_NOTIFICATIONS_ENABLED:
        raise SystemExit(
            "Refusing local login because outbound notifications are enabled."
        )
    if database["HOST"] not in {"127.0.0.1", "localhost"} or str(
        database["PORT"]
    ) != "55432":
        raise SystemExit(
            "Refusing local login because PostgreSQL is not the isolated local database."
        )

    team_id = int(sys.argv[1])
    team = Team.objects.select_related("owner").filter(pk=team_id).first()
    if team is None:
        raise SystemExit(f"Team {team_id} does not exist.")

    user = team.owner
    participant = Participant.objects.filter(team=team, claimed_by=user).first()
    refresh = RefreshToken.for_user(user)
    print(
        json.dumps(
            {
                "accessToken": str(refresh.access_token),
                "refreshToken": str(refresh),
                "kakaoProfile": {
                    "id": user.id,
                    "kakao_id": str(user.kakao_id),
                    "nickname": user.kakao_nickname,
                    "profile_image_url": user.profile_image_url,
                    "kakao_scopes": user.kakao_scopes,
                },
                "adminName": user.kakao_nickname or user.username,
                "adminUserId": user.id,
                "participantName": participant.display_name if participant else None,
                "participantId": participant.id if participant else None,
                "score": participant.leaderboard_score if participant else None,
                "teamCode": team.code,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
