from django.db import migrations


NICKNAMES = [
    "행복한 클로디", "신나는 마니", "다정한 클로디", "포근한 마니", "반짝이는 클로디", "용감한 마니",
    "설레는 클로디", "웃는 마니", "달콤한 클로디", "부지런한 마니", "호기심 많은 클로디", "따뜻한 마니",
    "장난꾸러기 클로디", "빛나는 마니", "느긋한 클로디", "응원하는 마니", "몽글몽글 클로디", "선물 든 마니",
    "별빛 클로디", "수줍은 마니", "꿈꾸는 클로디", "힘찬 마니", "산뜻한 클로디", "도토리 마니",
    "하늘빛 클로디", "반가운 마니", "씩씩한 클로디", "마음 따뜻한 마니", "구름 위 클로디", "행복 배달 마니",
]
AVATAR_KEYS = {
    "마니": [f"mani-{index}" for index in range(9)],
    "클로디": [f"clodi-{index}" for index in range(9)],
}


def profile_pairs():
    nickname_indexes = {"마니": {}, "클로디": {}}
    character_counts = {"마니": 0, "클로디": 0}
    for nickname in NICKNAMES:
        character = "클로디" if nickname.endswith("클로디") else "마니"
        nickname_indexes[character][nickname] = character_counts[character]
        character_counts[character] += 1

    pairs = []
    for avatar_round in range(9):
        for nickname in NICKNAMES:
            character = "클로디" if nickname.endswith("클로디") else "마니"
            avatar_key = AVATAR_KEYS[character][
                (nickname_indexes[character][nickname] + avatar_round) % len(AVATAR_KEYS[character])
            ]
            pairs.append((nickname, avatar_key))
    return pairs


def reassign_profiles(apps, schema_editor):
    Participant = apps.get_model("teams", "Participant")
    pairs = profile_pairs()
    team_ids = Participant.objects.order_by("team_id").values_list("team_id", flat=True).distinct()
    for team_id in team_ids:
        participants = list(Participant.objects.filter(team_id=team_id).order_by("created_at", "id"))
        for index, participant in enumerate(participants):
            participant.leaderboard_nickname, participant.leaderboard_avatar_key = pairs[index % len(pairs)]
            participant.save(update_fields=["leaderboard_nickname", "leaderboard_avatar_key"])


class Migration(migrations.Migration):
    dependencies = [("teams", "0007_participant_last_visit_score_at_and_more")]

    operations = [migrations.RunPython(reassign_profiles, migrations.RunPython.noop)]
