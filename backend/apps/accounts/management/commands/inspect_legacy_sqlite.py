import hashlib
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from apps.accounts.database_copy import (
    business_models,
    database_vendor,
    sqlite_preflight_errors,
)


class Command(BaseCommand):
    help = "읽기 전용 legacy SQLite의 이관 전 무결성과 기준 정보를 확인합니다."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="legacy")

    def handle(self, *args, **options):
        source_alias = options["source"]
        if database_vendor(source_alias) != "sqlite":
            raise CommandError(f"{source_alias} 데이터베이스가 SQLite가 아닙니다.")

        errors = sqlite_preflight_errors(source_alias)
        if errors:
            raise CommandError("; ".join(errors))

        sqlite_path = Path(os.environ["LEGACY_SQLITE_PATH"]).resolve()
        digest = hashlib.sha256()
        with open(sqlite_path, "rb") as sqlite_file:
            for chunk in iter(lambda: sqlite_file.read(1024 * 1024), b""):
                digest.update(chunk)

        connection = connections[source_alias]
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
            table_names = [row[0] for row in cursor.fetchall()]
            total_rows = 0
            for table_name in table_names:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {connection.ops.quote_name(table_name)}"
                )
                total_rows += cursor.fetchone()[0]

        business_rows = sum(
            model._default_manager.using(source_alias).count()
            for model in business_models()
        )
        self.stdout.write(
            self.style.SUCCESS(
                "SQLite 이관 전 검사 성공: "
                f"sha256={digest.hexdigest()} bytes={sqlite_path.stat().st_size} "
                f"tables={len(table_names)} total_rows={total_rows} "
                f"business_rows={business_rows} integrity=ok foreign_key_errors=0"
            )
        )
