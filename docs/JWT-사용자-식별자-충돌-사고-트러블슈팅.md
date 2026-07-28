# JWT 사용자 식별자 충돌 사고 트러블슈팅

> 작성일: 2026-07-28  
> 대상: MyManito 서비스 JWT 인증, REST API, 실시간 WebSocket 인증  
> 보안 주의: 이 문서에는 실제 사용자 이름, 카카오 ID, JWT 원문, 푸시 endpoint를 기록하지 않는다.

## 1. 요약

운영 SQLite DB를 이전 스냅샷으로 교체한 뒤, 교체 전 DB에서 발급된 장기 서비스 JWT가 교체 후 같은 정수 PK를 받은 다른 사용자를 인증하는 사고가 발생했다.

기존 JWT는 카카오의 고유 사용자 식별자가 아니라 Django `User.id`를 `user_id` claim으로 저장했다. SQLite DB 교체로 원래 사용자 행은 사라졌지만 브라우저의 JWT는 남았고, 이후 다른 사용자가 같은 `User.id`를 재사용하면서 기존 JWT가 새 사용자 계정으로 해석됐다. 그 결과 제보자는 자신이 Claim하지 않은 참가자의 일반 채팅과 개발자 피드백 채팅에 접근할 수 있었다.

근본 해결은 다음과 같다.

- JWT 사용자 식별자를 DB PK에서 고유 `kakao_id`로 변경한다.
- Django 비밀 키와 분리한 `JWT_SIGNING_KEY`를 도입하고 교체하여 기존 JWT를 전부 무효화한다.
- REST와 WebSocket이 동일한 SimpleJWT 인증 로직을 사용하게 한다.
- access JWT를 15분, refresh JWT를 30일로 제한한다.
- 수동 로그아웃 시 refresh JWT를 서버 블랙리스트에 등록한다.
- 강제 로그아웃은 게임·Claim·채팅·알림 설정·Web Push 구독을 변경하지 않는다.

## 2. 사용자에게 나타난 현상

- 팀 참가자 명단에는 제보자의 이름이 미Claim 상태로 남아 있었다.
- 제보자에 해당하는 회원가입 행과 일반 채팅 활동은 현재 DB에서 발견되지 않았다.
- 제보자의 브라우저에서는 다른 참가자가 사용하는 두 일반 채팅방이 열렸다.
- 개발자 피드백 채팅에서도 다른 사용자가 작성한 과거 메시지와 제보자의 메시지가 같은 스레드에 나타났다.
- 서버 DB에서 제보자의 메시지는 다른 사용자의 `User.id`로 기록됐다.

채팅 권한 검사 자체가 우회된 것은 아니었다. 서버가 JWT를 통해 잘못된 `request.user`를 확정한 뒤, 채팅 권한 로직이 그 사용자의 정상적인 Claim과 채팅방을 반환한 것이었다.

## 3. 확인된 사실과 추정 구간

### 3.1 확인된 사실

- 복구에 사용한 DB에는 특정 정수 PK까지의 사용자만 존재했다.
- DB 교체 후 최초로 가입한 사용자에게 바로 다음 정수 PK가 할당됐다.
- 제보자의 요청과 개발자 피드백 메시지는 그 신규 사용자의 PK로 인증·저장됐다.
- 기존 서비스 JWT의 기본 사용자 claim은 `user_id=User.id`였다.
- REST 인증은 SimpleJWT가 `User.id`로 사용자를 조회했고, WebSocket 미들웨어도 `token["user_id"]`로 `User.pk`를 직접 조회했다.
- 브라우저는 서비스 access/refresh JWT를 `localStorage`에 보관했다.
- 기존 JWT 수명은 access 30일, refresh 60일로 길었다.
- JWT 발급 경로는 Django `login()`을 호출하지 않아 모든 사용자의 `last_login`이 비어 있었고, 사용자별 접속 감사 로그도 없었다.

### 3.2 높은 신뢰도의 추정

교체 직전 운영 DB 또는 제보자 브라우저의 당시 refresh JWT를 보존하지 못했기 때문에 다음 과정 전체를 직접 증명하지는 못했다. 다만 DB 생성 시각, PK 할당 순서, 제보 메시지의 실제 발신자 PK, 현재 Claim 상태가 모두 아래 흐름과 일치한다.

```text
복구용 DB 스냅샷 생성
  ↓
운영 서비스에서 사용자 A가 가입해 PK N과 JWT(user_id=N)를 받음
  ↓
이전 스냅샷 DB로 운영 DB 교체
  ↓
사용자 A의 DB 행은 소실되지만 브라우저 JWT는 유지
  ↓
사용자 B가 가입하면서 같은 PK N을 재사용
  ↓
사용자 A의 기존 JWT가 현재 DB의 사용자 B로 인증됨
  ↓
사용자 B의 Claim, 일반 채팅, 개발자 피드백 채팅에 접근
```

이 가설을 완전히 확정하려면 교체 직전 DB에서 PK 매핑을 확인하거나, 제보자 refresh JWT의 원문을 노출하지 않고 `user_id`, `iat`, `exp`만 추출해 발급 시각과 PK를 대조해야 했다.

## 4. 기존 JWT 인증 체계의 문제

### 4.1 저장소 PK를 영구 신원으로 사용

`User.id`는 현재 DB 안에서 행을 참조하기 위한 내부 키다. DB 스냅샷 복원, 데이터 이관, 행 삭제·재생성 같은 작업이 발생하면 과거와 현재의 동일한 숫자가 같은 사람을 의미한다고 보장할 수 없다.

반면 장기 JWT는 DB 밖의 브라우저에 독립적으로 남는다. DB 상태가 과거로 돌아가도 JWT는 함께 돌아가지 않으므로, `User.id`를 장기 신원으로 사용하면 두 상태 사이에 신원 충돌이 발생할 수 있다.

### 4.2 장기 토큰과 서버 측 폐기 수단 부재

기존 access JWT는 30일, refresh JWT는 60일 동안 유효했다. 브라우저를 닫아도 `localStorage`가 유지되므로 DB 교체 후에도 토큰이 계속 사용될 수 있었다.

또한 JWT 전용 서명 키와 refresh 블랙리스트가 없어 다음 문제가 있었다.

- 특정 refresh JWT를 수동 로그아웃으로 폐기할 수 없었다.
- 사고 발생 시 Django의 다른 서명 기능에 영향을 주지 않고 서비스 JWT만 일괄 무효화하기 어려웠다.
- 사용자가 직접 세션을 종료할 수 있는 로그아웃 UI가 없었다.

### 4.3 REST와 WebSocket 인증 구현 중복

REST는 DRF SimpleJWT 인증을 사용했지만 WebSocket은 claim 이름과 `User.pk` 조회를 직접 구현했다. 인증 정책을 변경할 때 한쪽만 수정될 가능성이 있었고, 두 경로가 동일한 신원 규칙을 따른다는 보장이 코드 구조상 약했다.

### 4.4 로그인 감사 정보 부재

서비스 JWT 발급 시 Django의 `last_login`을 갱신하지 않았고, 익명 사용량 통계는 사용자별 이벤트를 저장하지 않았다. 개인정보 최소 수집에는 부합했지만 사고 발생 후 다음 사실을 확인할 수 없었다.

- 해당 카카오 계정이 언제 서비스 JWT를 새로 발급받았는가
- 현재 요청이 신규 로그인인지 브라우저에 남은 refresh JWT 갱신인지
- DB 교체 전 운영 DB에서 마지막으로 생성된 사용자 PK가 무엇인가

## 5. 해결 방법

### 5.1 JWT 신원 claim을 `kakao_id`로 변경

SimpleJWT 설정을 다음 정책으로 변경했다.

```python
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "SIGNING_KEY": JWT_SIGNING_KEY,
    "USER_ID_FIELD": "kakao_id",
    "USER_ID_CLAIM": "kakao_id",
}
```

`kakao_id`는 카카오 애플리케이션 내에서 사용자에게 부여되는 고유값이며 `User` 모델에서 unique 제약으로 보호된다. 과거 JWT의 `kakao_id`에 해당하는 사용자가 현재 DB에 없으면 인증은 401로 실패한다. 다른 사용자가 같은 DB PK를 재사용해도 그 사용자로 인증되지 않는다.

### 5.2 JWT 전용 서명 키 분리와 전 사용자 강제 만료

운영 환경에 별도 `JWT_SIGNING_KEY`를 필수로 두었다. 이 값이 없으면 운영 백엔드는 시작하지 않는다.

새 키를 생성해 배포하면 기존 키로 서명된 access/refresh JWT는 REST와 WebSocket에서 모두 즉시 거부된다. Django의 `DJANGO_SECRET_KEY`, 카카오 토큰, FCM/VAPID 키는 변경하지 않는다.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

생성한 값은 NAS의 `backend/.env`에만 저장한다.

```env
JWT_SIGNING_KEY=생성한_비밀값
```

이전 키를 복구하면 폐기된 JWT가 다시 유효해지므로 롤백 시에도 이전 JWT 키를 복원하면 안 된다.

### 5.3 REST와 WebSocket 인증 통합

WebSocket 미들웨어의 직접 `User.pk` 조회를 제거하고 DRF `JWTAuthentication`과 동일한 토큰 검증·사용자 조회를 사용하도록 변경했다.

인증 이후의 Redis 그룹명은 기존 `user.<User.id>`를 유지한다. 그룹명은 현재 연결에서 이벤트를 라우팅하는 내부 주소일 뿐 장기 신원 claim이 아니므로 기존 이벤트 발행 구조를 변경할 필요가 없다.

### 5.4 수동 로그아웃과 refresh 블랙리스트

`POST /api/accounts/logout/`은 현재 로그인 사용자의 refresh JWT만 블랙리스트에 등록한다.

- 사용자를 차단하거나 카카오 계정을 해제하는 기능이 아니다.
- 로그아웃한 브라우저의 refresh JWT만 다시 사용할 수 없게 한다.
- 다른 브라우저와 기기의 로그인 세션에는 영향을 주지 않는다.
- 이미 블랙리스트된 refresh JWT에 대한 재요청은 멱등 성공으로 처리한다.
- 다른 사용자의 refresh JWT는 거부한다.

현재 브라우저에서는 access/refresh JWT를 즉시 삭제하고 WebSocket을 닫는다. 이미 외부로 복사된 access JWT는 최대 15분간 유효할 수 있지만, refresh JWT는 더 이상 access를 재발급할 수 없다. 보안 사고의 전 사용자 강제 로그아웃은 서명 키를 교체하므로 access와 refresh가 모두 즉시 무효화된다.

### 5.5 브라우저 종료와 자동 갱신 정책

브라우저나 iOS 홈 화면 앱을 닫는 것은 로그아웃이 아니다. JWT는 기존처럼 `localStorage`에 유지된다.

- access JWT 만료 전 재접속: 기존 access 사용
- access JWT 만료 후 재접속: refresh JWT로 access를 백그라운드에서 재발급
- 알림 딥링크 진입: 자동 갱신 후 원래 경로로 이동
- refresh JWT 발급 후 30일 경과: 카카오 재로그인 필요
- refresh JWT는 회전하지 않으므로 30일 만료는 마지막 사용 시점이 아니라 발급 시점 기준

### 5.6 푸시 구독과 게임 데이터 보존

서명 키 교체는 JWT 검증 정책만 변경한다. 다음 데이터는 삭제하거나 다시 연결하지 않는다.

- User 및 카카오 OAuth 토큰
- Team, Participant, Claim, 배정 결과
- 일반 채팅, 개발자 피드백 채팅, 익명 프로필
- 앱 내 알림과 사용자 알림 설정
- Android `WebPushDevice`
- iOS `IOSWebPushSubscription`

따라서 강제 로그아웃 후 같은 카카오 계정으로 재로그인하면 기존 게임과 채팅이 그대로 나타나며, 기존 푸시 구독도 유지된다.

사용자가 직접 누르는 수동 로그아웃만 현재 기기의 푸시 구독 해제를 먼저 시도한다. 다른 기기 구독과 계정의 알림 설정은 보존한다. 푸시 구독 해제 API가 실패해도 로컬 JWT 삭제와 WebSocket 종료는 반드시 수행한다.

### 5.7 최소 로그인 감사 정보 추가

성공한 카카오 로그인에서 기존 `last_login` 필드를 갱신한다. 별도 IP, User-Agent, JWT 원문은 저장하지 않는다. 이는 개인정보 수집을 확대하지 않으면서 마지막 신규 로그인 시각을 확인하기 위한 최소 조치다.

## 6. 설계 단계에서 놓친 점

### 6.1 인증 식별자와 DB 참조 키를 구분하지 않음

unique인 `User.id`를 불변 신원으로 간주했다. 정수 PK는 현재 DB 안에서만 unique하며, 외부에 장기간 보관되는 토큰의 영구 신원으로 적합하지 않다.

설계 단계에서 다음 질문이 필요했다.

> DB를 복원·이관하거나 사용자를 삭제·재생성해도 이 claim이 같은 사람만 가리키는가?

### 6.2 DB 복구 범위를 도메인 데이터에만 한정

팀 배정, 채팅, 알림, Claim 무결성은 검증했지만 운영 DB 교체가 이미 발급된 인증 토큰과 사용자 PK 매핑에 미치는 영향을 검토하지 않았다.

DB 복구 체크리스트에는 도메인 데이터뿐 아니라 다음 항목이 포함돼야 한다.

- 사용자 PK와 외부 고유 식별자 매핑
- 복구 시점 이후 생성된 사용자와 발급된 세션
- DB 밖에 남아 있는 JWT, 쿠키, API 키
- 기존 WebSocket 연결
- 푸시 구독과 사용자 소유 관계

### 6.3 운영 서비스가 쓰는 중에 스냅샷 DB로 교체

스냅샷 생성 후 실제 교체까지 운영 쓰기가 계속되면 그 사이 가입·Claim·메시지가 새 DB에 포함되지 않는다. 파일 교체가 성공해도 논리적으로는 데이터 유실과 신원 시간 역행이 발생한다.

운영 DB를 복구하거나 이관할 때는 다음 원칙을 지켜야 한다.

1. 유지보수 모드로 신규 로그인과 쓰기를 차단한다.
2. 중단 후 최신 운영 DB를 백업한다.
3. 백업 크기, 테이블, 무결성, 사용자 PK 매핑을 검증한다.
4. 가능하면 전체 파일을 과거 상태로 교체하지 말고 최신 운영 DB에 필요한 레코드만 수정한다.
5. 전체 교체가 불가피하면 모든 외부 세션을 함께 무효화한다.

### 6.4 인증 로직의 단일 진실 공급원 부재

REST와 WebSocket이 서로 다른 사용자 조회 코드를 가지고 있었다. 인증 claim이나 사용자 필드를 바꿀 때 두 경로가 어긋날 수 있었다. 인증·인가 경계는 가능한 한 같은 라이브러리와 설정을 통해 검증해야 한다.

### 6.5 강제 세션 폐기와 사용자 로그아웃을 초기 설계에서 제외

JWT는 상태가 없다는 이유로 발급만 구현하고 폐기·회전·사고 대응을 뒤로 미뤘다. 그러나 운영 서비스에는 최소한 다음 기능이 필요하다.

- 사용자 자신의 수동 로그아웃
- refresh JWT 서버 측 폐기
- 전 사용자 JWT 서명 키 교체
- 폐기된 키를 복구하지 않는 롤백 정책
- 짧은 access JWT와 UX를 보완하는 refresh JWT

### 6.6 인증 사고 회귀 테스트 부재

정상 로그인과 refresh 성공만 테스트했고 다음 시나리오가 없었다.

- 과거 사용자의 DB PK를 다른 사용자가 재사용
- 폐기된 서명 키로 만든 access/refresh
- REST는 거부하지만 WebSocket은 허용하는 정책 불일치
- 로그아웃한 refresh JWT의 재사용
- 로그아웃 과정에서 다른 기기의 푸시 구독 삭제

## 7. 회귀 테스트와 검증

다음 테스트를 추가하고 검증했다.

- JWT payload에 `user_id`가 없고 `kakao_id`가 포함되는지 확인
- 사용자 A 삭제 후 사용자 B가 같은 DB PK를 재사용해도 A의 JWT로 B를 인증하지 않는지 확인
- 폐기된 키로 서명한 JWT를 REST와 WebSocket에서 모두 거부하는지 확인
- 유효 refresh JWT로 access를 재발급하고, 수동 로그아웃 후 동일 refresh를 거부하는지 확인
- 다른 사용자의 refresh JWT를 로그아웃할 수 없는지 확인
- 로그아웃 API 자체는 푸시 구독과 알림 설정을 삭제하지 않는지 확인
- iOS 구독 삭제 API가 현재 사용자의 지정 endpoint만 삭제하는지 확인
- WebSocket 사용자별 그룹 격리와 401 성격의 `4401` 종료를 확인
- access 15분, refresh 30일, refresh 비회전 정책을 확인

작성 시점 검증 결과:

- 백엔드 전체 테스트 72개 통과
- 프론트엔드 프로덕션 빌드 통과
- Docker Compose 설정 검증 통과
- 구현 과정 전후 운영 SQLite 사본의 SHA-256 해시 동일
- 기존 Team·Participant·Claim·채팅·알림·푸시 데이터 변경 없음

## 8. 안전한 배포 절차

1. 운영 DB를 백업하고 크기, 테이블, 무결성 검사 결과를 확인한다.
2. User, Participant/Claim/배정, 일반·개발자 채팅, Notification, WebPushDevice, IOSWebPushSubscription의 배포 전 건수와 핵심 매핑을 기록한다.
3. 신뢰할 수 있는 환경에서 새 `JWT_SIGNING_KEY`를 한 번 생성한다.
4. NAS `backend/.env`에 키를 저장하되 저장소와 프론트엔드에는 넣지 않는다.
5. DB 파일을 교체하지 않고 새 백엔드·프론트엔드 이미지만 배포한다.
6. 토큰 블랙리스트 migration을 적용하고 백엔드를 재시작한다.
7. 재시작으로 기존 WebSocket 연결을 모두 끊고, 재연결되는 구 JWT를 `4401`로 거부한다.
8. 보관한 구 토큰 표본으로 REST access·refresh가 401인지 확인한 뒤 표본을 폐기한다.
9. 새 카카오 로그인으로 기존 팀, Claim, 양쪽 채팅방, 개발자 채팅, 알림 설정과 실시간 연결을 확인한다.
10. 배포 전후 도메인 데이터와 푸시 구독 건수·소유 관계가 동일한지 확인한다.

오프라인 브라우저의 `localStorage`를 서버가 원격으로 직접 삭제할 수는 없다. 하지만 구 JWT는 서버에서 즉시 무효이므로 다음 접속 시 REST refresh 실패 또는 WebSocket `4401`을 통해 로컬 세션을 자동 삭제하고 로그인 화면으로 이동한다.

## 9. 향후 예방 원칙

- 외부 세션 claim에는 DB 자동 증가 PK 대신 재사용되지 않는 외부 고유 ID 또는 UUID를 사용한다.
- DB 복구·이관과 인증 세션 무효화 계획을 하나의 변경 작업으로 취급한다.
- 운영 DB를 교체할 때는 쓰기 중단 시점을 명확히 하고 그 이후 변경분이 없음을 검증한다.
- REST, WebSocket, 백그라운드 작업은 동일한 인증 설정과 사용자 조회 규칙을 사용한다.
- access JWT는 짧게 유지하고 refresh JWT로 UX를 보완한다.
- 브라우저 종료, 수동 로그아웃, 강제 로그아웃의 동작을 서로 구분한다.
- 보안 사고 롤백에서 폐기한 JWT 서명 키를 다시 활성화하지 않는다.
- 토큰 원문은 로그·문서·채팅·저장소에 기록하지 않는다.

## 10. 관련 구현 위치

- JWT 설정과 운영 키 검증: `backend/config/settings.py`
- 카카오 로그인·수동 로그아웃·푸시 구독 API: `backend/apps/accounts/views.py`
- REST API URL: `backend/apps/accounts/urls.py`
- WebSocket JWT 인증: `backend/apps/realtime/middleware.py`
- 프론트 세션 저장·강제 만료: `frontend/src/stores/auth.js`, `frontend/src/api/index.js`
- WebSocket `4401` 처리: `frontend/src/stores/realtime.js`
- 현재 기기 수동 로그아웃: `frontend/src/views/NotificationSettingsView.vue`
- 보안 회귀 테스트: `backend/apps/accounts/tests.py`, `backend/apps/realtime/tests.py`

