from django.core.management.base import BaseCommand, CommandError

from apps.accounts.database_copy import (
    compare_database_copy,
    constraint_errors,
    database_vendor,
    identity_errors,
    media_errors,
    sequence_errors,
)


class Command(BaseCommand):
    help = "읽기 전용 SQLite 원본과 PostgreSQL 대상의 업무 데이터를 비교합니다."

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

        results, errors = compare_database_copy(source_alias, target_alias)
        total_count = 0
        for result in results:
            total_count += result["count"]
            status = "OK" if result["matches"] else "MISMATCH"
            self.stdout.write(
                f"{status} {result['model']}: count={result['count']} sha256={result['aggregate']}"
            )

        for error in errors:
            self.stderr.write(
                "MISMATCH "
                f"{error['model']}: source={error['source_count']} target={error['target_count']} "
                f"missing={error['missing_target_pks']} "
                f"unexpected={error['unexpected_target_pks']} "
                f"changed={error['mismatched_pks']} "
                f"fields={error['mismatched_fields']}"
            )

        validation_errors = [
            *constraint_errors(target_alias),
            *identity_errors(source_alias, target_alias),
            *sequence_errors(target_alias),
        ]
        media_reference_count, missing_media = media_errors(target_alias)
        validation_errors.extend(missing_media)
        if errors or validation_errors:
            for error in validation_errors:
                self.stderr.write(error)
            raise CommandError("데이터베이스 이관 검증에 실패했습니다.")

        self.stdout.write(
            self.style.SUCCESS(
                f"데이터베이스 이관 검증 성공: rows={total_count}, media_references={media_reference_count}"
            )
        )
