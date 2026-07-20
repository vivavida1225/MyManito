"""리더보드 점수 규칙과 게임 프로필 프리셋."""

CHAT_MESSAGE_POINTS = 2
CHAT_LIKE_POINTS = 3
TEAM_VISIT_POINTS = 1

CARED_FOR_TO_MANITO_MULTIPLIER = 3

CHAT_MESSAGE_COOLDOWN_MINUTES = 30
CHAT_MESSAGE_DAILY_LIMIT = 6
CHAT_LIKE_COOLDOWN_HOURS = 6
TEAM_VISIT_COOLDOWN_HOURS = 6

LEADERBOARD_NICKNAMES = [
    "행복한 클로디", "신나는 마니", "다정한 클로디", "포근한 마니",
    "반짝이는 클로디", "용감한 마니", "설레는 클로디", "웃는 마니",
    "달콤한 클로디", "부지런한 마니", "호기심 많은 클로디", "따뜻한 마니",
    "장난꾸러기 클로디", "빛나는 마니", "느긋한 클로디", "응원하는 마니",
    "몽글몽글 클로디", "선물 든 마니", "별빛 클로디", "수줍은 마니",
    "꿈꾸는 클로디", "힘찬 마니", "산뜻한 클로디", "도토리 마니",
    "하늘빛 클로디", "반가운 마니", "씩씩한 클로디", "마음 따뜻한 마니",
    "구름 위 클로디", "행복 배달 마니",
]
LEADERBOARD_AVATAR_KEYS = [
    *(f"mani-{index}" for index in range(9)),
    *(f"clodi-{index}" for index in range(9)),
]
