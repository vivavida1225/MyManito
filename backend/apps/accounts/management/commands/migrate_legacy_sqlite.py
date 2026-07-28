import os
import tempfile
from itertools import chain

from django.core import serializers
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.database_copy import (
    FullPrecisionDjangoJSONEncoder,
    business_models,
    compare_database_copy,
    database_vendor,
    nonempty_business_models,
    sqlite_preflight_errors,
)


class Command(BaseCommand):
    help = "읽기 전용 legacy SQLite 업무 데이터를 빈 PostgreSQL로 이관합니다."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="legacy")
        parser.add_argument("--target", default="default")

    def handle(self, *args, **options):
        source_alias = options["source"]
        target_alias = options["target"]
        if database_vendor(source_alias) != "sqlite":
            raise CommandError(f"{source_alias} 데이터베이스가 SQLite가 아닙니다.")
        if database_vendor(target_alias) != "postgresql":
            raise CommandError(f"{target_alias} 데이터베이스가 PostgreSQL이 아닙니다.")
        preflight_errors = sqlite_preflight_errors(source_alias)
        if preflight_errors:
            raise CommandError("; ".join(preflight_errors))

        nonempty_models = nonempty_business_models(target_alias)
        if nonempty_models:
            raise CommandError(
                "대상 PostgreSQL 업무 테이블이 비어 있지 않습니다: "
                + ", ".join(nonempty_models)
            )

        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="mymanito-sqlite-",
                suffix=".json",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name

            source_objects = chain.from_iterable(
                model._default_manager.using(source_alias).order_by(
                    model._meta.pk.name
                )
                for model in business_models()
            )
            with open(temporary_path, "w", encoding="utf-8") as fixture_file:
                serializers.serialize(
                    "json",
                    source_objects,
                    stream=fixture_file,
                    cls=FullPrecisionDjangoJSONEncoder,
                )
            call_command(
                "loaddata",
                temporary_path,
                database=target_alias,
                verbosity=1,
            )
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.remove(temporary_path)

        results, errors = compare_database_copy(source_alias, target_alias)
        if errors:
            raise CommandError(
                "데이터 적재 후 canonical 비교에 실패했습니다. "
                "서비스를 시작하지 말고 PostgreSQL 대상을 초기화한 뒤 다시 실행하세요."
            )
        row_count = sum(result["count"] for result in results)
        self.stdout.write(
            self.style.SUCCESS(f"SQLite 업무 데이터 적재 성공: rows={row_count}")
        )
