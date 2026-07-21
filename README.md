# MyManito (마이마니또)

카카오 로그인으로 쉽고 안전하게 즐기는 **모바일 퍼스트 마니또 게임 플랫폼**입니다. 팀을 만들고, 익명으로 대화하고, 게임이 끝난 뒤 설레는 결과를 확인할 수 있습니다.

> 서비스 주소: [mymanito.wara.synology.me](https://mymanito.wara.synology.me)

## 기획 의도

마니또 게임은 여전히 단체 채팅방, 스프레드시트, 개인 연락처에 의존하는 경우가 많습니다. 참여자 명단 관리, 랜덤 배정, 오매칭 처리, 익명 대화, 결과 공개까지 모두 한 명의 관리자에게 집중되고, 관리자는 다른 참여자의 배정 정보를 알게 되므로 게임에 공정하게 참여하기 어렵습니다.

MyManito는 이 문제를 해결하기 위해 만들었습니다.

- **관리자도 참여자와 함께 게임에 참여**할 수 있습니다. 관리자는 진행 상황만 관리할 수 있고, 게임이 끝나기 전에는 타인의 배정 결과를 볼 수 없습니다.
- 팀 코드를 통한 간단한 입장과 강한 본인 확인으로 **이름 오선택과 무단 참여를 줄입니다.**
- 관계별 1:1 익명 채팅과 카카오톡 알림으로 **마니또 활동을 자연스럽게 이어갑니다.**
- 결과 공개 방식과 종료 예정일을 관리자가 선택해 **소규모 모임부터 행사형 게임까지** 대응합니다.

## 주요 기능

- 카카오 OAuth 로그인 및 `talk_message` 권한 동의 안내
- 팀 코드 기반 팀 생성·참여, 참가자 명단 파싱, 게임 규칙 설정
- 자기 자신 지목 방지 및 상호 지목 허용 비율을 반영한 랜덤 배정
- 참가자 이름 선택 후 재확인을 거치는 Claim(본인 확인) 흐름
- 관리자 본인 참여 지원 및 Claim 진행률·미확인자·오매칭 초기화 관리
- 종료 예정일 D-Day, 자동 공개·관리자 외부 공개 방식 설정
- 관계별 1:1 익명 채팅, 읽음 처리, 이미지 압축 전송, 이모티콘 전송
- 3초 간격 HTTP Short Polling과 카카오톡 ‘나와의 채팅방’ 메시지 알림
- 팀별 익명 닉네임·프로필 설정, 기본 마니·클로디 프로필 제공
- 팀별 게임 전용 프로필과 리더보드: 채팅·좋아요·팀 접속 활동을 서버에서 점수화하고, 매시 정각 순위를 갱신
- 상위 3명 포디움과 4~123위 목록, 결과 공개 뒤 실제 이름·최종 점수 공개
- 게임 종료 후 결과 공개, 폭죽 효과, 종료 데이터 7일 보존 후 자동 정리

## 사용자 흐름

```text
카카오 로그인
  → 대시보드
  → 새 팀 만들기 / 팀 코드로 참여
  → 규칙 확인 및 본인 이름 Claim
  → 내가 챙겨줄 사람 확인
  → 익명 프로필 설정
  → 1:1 익명 채팅
  → 팀 리더보드 확인
  → 게임 종료 및 결과 공개
```

### 관리자 흐름

1. 팀 코드, 참가자, 규칙, 종료 예정일, 공개 방식을 설정해 팀을 생성합니다.
2. 참가자 Claim 현황과 미확인자 목록을 확인하고, 잘못 연결된 Claim은 해제합니다.
3. 진행 중에는 다른 참가자의 배정표를 볼 수 없습니다.
4. 게임 종료 시 팀 코드를 다시 입력해 실수를 방지합니다.
5. 자동 공개 또는 외부 공개 완료 처리로 참가자가 결과를 볼 수 있게 합니다.

## 화면 미리보기

| 로그인 · 권한 동의 | 대시보드 |
| --- | --- |
| <img src="docs/screenshots/1login.png" alt="카카오 로그인 화면" width="320"> | <img src="docs/screenshots/3main_dashboard.png" alt="메인 대시보드" width="320"> |

| 팀 만들기 | 팀 참여 |
| --- | --- |
| <img src="docs/screenshots/4make_team.png" alt="팀 생성 화면" width="320"> | <img src="docs/screenshots/6join_team.png" alt="팀 참여 화면" width="320"> |

| 이름 확인 | 배정 결과 |
| --- | --- |
| <img src="docs/screenshots/8join_team_select.png" alt="이름 선택 화면" width="320"> | <img src="docs/screenshots/10manito_confirm.png" alt="마니또 확인 화면" width="320"> |

| 채팅 목록 | 익명 채팅 |
| --- | --- |
| <img src="docs/screenshots/12chat_dashboard.png" alt="채팅 목록" width="320"> | <img src="docs/screenshots/13chat_ui.png" alt="익명 채팅방" width="320"> |

## 기술 스택

| 구분 | 기술 |
| --- | --- |
| Frontend | Vue 3 Composition API, Vite, Vue Router, Pinia, Tailwind CSS, Axios |
| UI/UX | Mobile-First UI, Canvas Confetti, browser-image-compression |
| Backend | Python, Django, Django REST Framework, Simple JWT |
| 인증·알림 | Kakao OAuth, Kakao Talk Message API |
| 데이터·파일 | SQLite, Pillow, 로컬 미디어 볼륨 |
| 작업 자동화 | APScheduler |
| 배포 | Docker Compose, Gunicorn, Nginx, Synology NAS |

## 아키텍처

```text
Browser (Vue 3)
        │ HTTPS
        ▼
Nginx ──────────────► /media 직접 서빙
        │ /api
        ▼
Gunicorn + Django REST Framework
        ├── SQLite
        ├── 로컬 media 볼륨
        ├── Kakao OAuth / Talk Message API
        └── APScheduler (보존 기간 정리)
```

WebSocket·Redis·Celery 대신 **3초 Short Polling**을 사용해, Synology NAS에서도 적은 컨테이너로 가볍게 운영할 수 있도록 구성했습니다.

## 익명성 및 데이터 보존 정책

- 채팅에서는 카카오 프로필 대신 팀·관계별 익명 닉네임과 프로필을 사용합니다.
- 리더보드는 별도의 게임 전용 별명·프로필을 사용하며, 진행 중에는 정확한 점수를 공개하지 않습니다.
- 결과가 공개되면 최종 순위, 실제 이름, 게임 별명과 최종 점수를 함께 확인할 수 있습니다.
- 관리자도 게임 진행 중에는 자신의 배정 외 다른 참가자의 매칭 정보를 볼 수 없습니다.
- 진행 중 팀에서 읽은 지 24시간이 지난 이미지 첨부 파일은 자동으로 정리됩니다.
- 종료된 팀의 결과, 채팅, 이미지 데이터는 7일 동안 보존한 뒤 자동으로 영구 삭제됩니다.
- 카카오톡 알림은 발신자를 특정하지 않는 문구와 채팅방 딥링크를 사용합니다.

## 시작하기

### 1. 환경 변수 설정

`backend/.env.example`, `frontend/.env.example`을 각각 복사해 `.env`를 만들고 카카오 개발자 콘솔 값과 배포 주소를 입력합니다.

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
```

주요 환경 변수는 다음과 같습니다.

| 파일 | 변수 | 설명 |
| --- | --- | --- |
| `backend/.env` | `DJANGO_SECRET_KEY` | Django 비밀 키 |
| `backend/.env` | `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET` | 카카오 OAuth 설정 |
| `backend/.env` | `KAKAO_REDIRECT_URI` | 카카오 로그인 콜백 주소 |
| `backend/.env` | `MYMANITO_APP_URL` | 카카오 메시지 링크에 사용할 서비스 주소 |
| `backend/.env` | `FIREBASE_SERVICE_ACCOUNT_JSON` | Android FCM 발송용 Firebase 서비스 계정 JSON 전체(서버 전용) |
| `backend/.env` | `IOS_WEB_PUSH_VAPID_PRIVATE_KEY`, `IOS_WEB_PUSH_VAPID_SUBJECT` | iOS 표준 Web Push VAPID 비공개 키와 연락처(서버 전용) |
| `frontend/.env` | `VITE_KAKAO_REST_API_KEY` | 프론트엔드 카카오 REST API 키 |
| `frontend/.env` | `VITE_API_BASE_URL` | API 기본 경로 |
| `frontend/.env` | `VITE_IOS_WEB_PUSH_VAPID_PUBLIC_KEY` | iOS VAPID 비공개 키와 쌍인 공개 키 |

카카오 개발자 콘솔에서 `talk_message` 동의 항목과 등록된 Redirect URI를 함께 설정해야 메시지 알림을 받을 수 있습니다.

### Firebase 기기 알림 설정

제공된 Firebase 웹 설정과 VAPID 공개 키는 프론트엔드에 연결되어 있습니다. 실제 FCM 발송에는 공개 웹 설정과 별도로 **Firebase 서비스 계정 비공개 키**가 필요합니다. Firebase Console의 **프로젝트 설정 → 서비스 계정 → 새 비공개 키 생성**에서 JSON을 내려받아 한 줄 JSON으로 만든 뒤 `backend/.env`의 `FIREBASE_SERVICE_ACCOUNT_JSON`에 넣으세요. 이 값은 절대로 `frontend/.env`나 저장소에 넣으면 안 됩니다.

배포 URL은 HTTPS여야 합니다. 배포 후 상단 설정 아이콘에서 Android를 선택하고 `이 기기 알림 켜기`를 누르면 Chrome FCM 알림을 등록합니다. 새 메시지, 참여 확인, D-Day, 관리자 공지, 결과 공개가 발생할 때 앱 내 알림과 기기 푸시가 함께 전송됩니다.

### iPhone · iPad 기기 알림 설정

iOS 16.4 이상은 Firebase FCM이 아닌 표준 Web Push를 사용합니다. VAPID 키 쌍을 생성해 비공개 키는 `backend/.env`의 `IOS_WEB_PUSH_VAPID_PRIVATE_KEY`, 공개 키는 `frontend/.env`의 `VITE_IOS_WEB_PUSH_VAPID_PUBLIC_KEY`에 넣고, `IOS_WEB_PUSH_VAPID_SUBJECT`에는 운영자 연락처(예: `mailto:admin@example.com`)를 설정하세요. Firebase VAPID 키와 iOS VAPID 키는 별개입니다.

사용자는 Safari 또는 Chrome의 공유 메뉴에서 MyManito를 **홈 화면에 추가**한 뒤, 홈 화면 아이콘으로 앱을 열어 상단 설정 아이콘에서 iPhone · iPad를 선택하고 알림을 허용해야 합니다. 일반 브라우저 탭에서는 iOS 기기 알림을 받을 수 없습니다.

### 2. Docker로 실행

```powershell
docker compose up -d --build
```

- 프론트엔드: `http://localhost:8080`
- API: Nginx를 통해 `/api/` 경로로 접근
- 영속 데이터: `data/db.sqlite3`, `data/media`, `data/static`

### 3. 개발 서버 실행

```powershell
# backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# frontend (별도 터미널)
cd frontend
npm install
npm run dev
```

## 검증 명령

```powershell
# Backend
cd backend
python manage.py test

# Frontend
cd frontend
npm run build
```

## 문서

- [기획 명세서](docs/명세서.md)
- [서비스 플로우 PDF](docs/my-manito-service-flow.pdf)
