#!/bin/sh

set -eu
umask 077

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_ROOT"

SQLITE_PATH="$PROJECT_ROOT/data/db.sqlite3"
MEDIA_PATH="$PROJECT_ROOT/data/media"
POSTGRES_PATH="$PROJECT_ROOT/data/postgres"
BACKUP_ROOT="$PROJECT_ROOT/data/migration-backups"
TIMESTAMP=$(date "+%Y%m%d-%H%M%S")
BACKUP_PATH="$BACKUP_ROOT/sqlite-$TIMESTAMP"
DUMP_PATH="$BACKUP_ROOT/postgres-after-import-$TIMESTAMP.dump"
RESTORE_DATABASE="mymanito_restore_verify_$(date "+%Y%m%d%H%M%S")"
RESTORE_CREATED=0

cleanup() {
  if [ "$RESTORE_CREATED" -eq 1 ]; then
    docker compose exec -T postgres sh -c \
      'dropdb --if-exists -U "$POSTGRES_USER" "$1"' sh "$RESTORE_DATABASE" >/dev/null
  fi
}
trap cleanup EXIT

if [ ! -f "$SQLITE_PATH" ]; then
  echo "ERROR: 최신 SQLite 파일을 찾을 수 없습니다: $SQLITE_PATH" >&2
  exit 1
fi

for suffix in -wal -shm -journal; do
  if [ -e "$SQLITE_PATH$suffix" ]; then
    echo "ERROR: SQLite sidecar 파일이 남아 있습니다: $SQLITE_PATH$suffix" >&2
    exit 1
  fi
done

if [ ! -d "$MEDIA_PATH" ]; then
  echo "ERROR: 미디어 디렉터리를 찾을 수 없습니다: $MEDIA_PATH" >&2
  exit 1
fi

for variable_name in POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD; do
  if ! grep -Eq "^${variable_name}=.+" backend/.env; then
    echo "ERROR: backend/.env에 ${variable_name} 값을 설정해 주세요." >&2
    exit 1
  fi
done

mkdir -p "$POSTGRES_PATH"
if [ -n "$(find "$POSTGRES_PATH" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
  echo "ERROR: PostgreSQL 데이터 디렉터리가 비어 있지 않습니다: $POSTGRES_PATH" >&2
  echo "기존 PostgreSQL을 덮어쓰지 않으므로 상태를 확인한 뒤 명시적으로 정리해 주세요." >&2
  exit 1
fi

docker compose config -q
docker compose stop backend frontend
docker compose build backend

docker compose run --rm --no-deps \
  --volume "$SQLITE_PATH:/migration/db.sqlite3:ro" \
  -e LEGACY_SQLITE_PATH=/migration/db.sqlite3 \
  -e SCHEDULER_ENABLED=false \
  backend python manage.py inspect_legacy_sqlite

mkdir -p "$BACKUP_ROOT"
mkdir "$BACKUP_PATH"
cp "$SQLITE_PATH" "$BACKUP_PATH/db.sqlite3"
cp -a "$MEDIA_PATH" "$BACKUP_PATH/media"
sha256sum "$SQLITE_PATH" "$BACKUP_PATH/db.sqlite3" > "$BACKUP_PATH/sha256.txt"
chmod -R a-w "$BACKUP_PATH"

docker compose up -d postgres redis

docker compose run --rm \
  -e SCHEDULER_ENABLED=false \
  backend python manage.py migrate --noinput

docker compose run --rm \
  --volume "$SQLITE_PATH:/migration/db.sqlite3:ro" \
  -e LEGACY_SQLITE_PATH=/migration/db.sqlite3 \
  -e SCHEDULER_ENABLED=false \
  backend python manage.py migrate_legacy_sqlite

docker compose run --rm \
  --volume "$SQLITE_PATH:/migration/db.sqlite3:ro" \
  -e LEGACY_SQLITE_PATH=/migration/db.sqlite3 \
  -e SCHEDULER_ENABLED=false \
  backend python manage.py verify_database_copy

docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$DUMP_PATH"

docker compose exec -T postgres sh -c \
  'createdb -U "$POSTGRES_USER" "$1"' sh "$RESTORE_DATABASE"
RESTORE_CREATED=1
docker compose exec -T postgres sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$1"' sh "$RESTORE_DATABASE" < "$DUMP_PATH"

docker compose run --rm \
  --volume "$SQLITE_PATH:/migration/db.sqlite3:ro" \
  -e LEGACY_SQLITE_PATH=/migration/db.sqlite3 \
  -e POSTGRES_DB="$RESTORE_DATABASE" \
  -e SCHEDULER_ENABLED=false \
  backend python manage.py verify_database_copy

echo "SQLite 백업: $BACKUP_PATH"
echo "PostgreSQL 백업: $DUMP_PATH"
echo "마이그레이션과 복구 검증이 완료되었습니다."
echo "서비스는 아직 시작하지 않았습니다. 승인 후 다음 명령을 실행하세요:"
echo "  docker compose up -d backend frontend"
