import hashlib
import json
from datetime import datetime
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connections, models, transaction
from django.db.models import Max


BUSINESS_MODEL_LABELS = (
    "accounts.User",
    "accounts.WebPushDevice",
    "accounts.IOSWebPushSubscription",
    "analytics.UsageMetric",
    "teams.Team",
    "teams.Participant",
    "chat.Message",
    "chat.MessageAttachment",
    "chat.ChatProfile",
    "chat.FeedbackThread",
    "chat.FeedbackMessage",
    "chat.FeedbackMessageAttachment",
    "chat.Notification",
    "teams.ScoreEvent",
    "teams.LeaderboardSnapshot",
)


class FullPrecisionDjangoJSONEncoder(DjangoJSONEncoder):
    def default(self, value):
        if isinstance(value, datetime):
            encoded = value.isoformat()
            if value.utcoffset() is not None:
                encoded = encoded.replace("+00:00", "Z")
            return encoded
        return super().default(value)


def business_models():
    return [apps.get_model(label) for label in BUSINESS_MODEL_LABELS]


def database_vendor(alias):
    return connections[alias].vendor


def nonempty_business_models(alias):
    return [
        model._meta.label
        for model in business_models()
        if model._default_manager.using(alias).exists()
    ]


def sqlite_preflight_errors(alias):
    connection = connections[alias]
    if connection.vendor != "sqlite":
        return [f"{alias} 데이터베이스가 SQLite가 아닙니다."]
    errors = []
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA integrity_check")
        integrity_result = cursor.fetchone()[0]
        if integrity_result != "ok":
            errors.append(f"SQLite integrity_check 실패: {integrity_result}")
        cursor.execute("PRAGMA foreign_key_check")
        foreign_key_issues = cursor.fetchall()
        if foreign_key_issues:
            errors.append(
                f"SQLite foreign_key_check 실패: issues={len(foreign_key_issues)}"
            )
    return errors


def canonical_model_state(model, alias):
    queryset = model._default_manager.using(alias).order_by(model._meta.pk.name)
    serialized = serializers.serialize(
        "json",
        queryset,
        cls=FullPrecisionDjangoJSONEncoder,
    )
    rows = json.loads(serialized)
    canonical_rows = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in rows
    ]
    row_hashes = {
        str(row["pk"]): hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        for row, canonical in zip(rows, canonical_rows, strict=True)
    }
    fields_by_pk = {
        str(row["pk"]): row["fields"]
        for row in rows
    }
    aggregate = hashlib.sha256(
        ("[" + ",".join(canonical_rows) + "]").encode("utf-8")
    ).hexdigest()
    return {
        "count": len(rows),
        "aggregate": aggregate,
        "row_hashes": row_hashes,
        "fields_by_pk": fields_by_pk,
    }


def compare_database_copy(source_alias, target_alias):
    results = []
    errors = []
    for model in business_models():
        source = canonical_model_state(model, source_alias)
        target = canonical_model_state(model, target_alias)
        source_pks = set(source["row_hashes"])
        target_pks = set(target["row_hashes"])
        mismatched_pks = sorted(
            (
                pk
                for pk in source_pks & target_pks
                if source["row_hashes"][pk] != target["row_hashes"][pk]
            ),
            key=int,
        )
        mismatched_fields = {
            pk: sorted(
                field_name
                for field_name in (
                    set(source["fields_by_pk"][pk])
                    | set(target["fields_by_pk"][pk])
                )
                if source["fields_by_pk"][pk].get(field_name)
                != target["fields_by_pk"][pk].get(field_name)
            )
            for pk in mismatched_pks[:20]
        }
        missing_target_pks = sorted(source_pks - target_pks, key=int)
        unexpected_target_pks = sorted(target_pks - source_pks, key=int)
        matches = (
            source["count"] == target["count"]
            and source["aggregate"] == target["aggregate"]
        )
        results.append(
            {
                "model": model._meta.label,
                "count": source["count"],
                "aggregate": source["aggregate"],
                "matches": matches,
            }
        )
        if not matches:
            errors.append(
                {
                    "model": model._meta.label,
                    "source_count": source["count"],
                    "target_count": target["count"],
                    "missing_target_pks": missing_target_pks[:20],
                    "unexpected_target_pks": unexpected_target_pks[:20],
                    "mismatched_pks": mismatched_pks[:20],
                    "mismatched_fields": mismatched_fields,
                }
            )
    return results, errors


def sequence_errors(alias):
    connection = connections[alias]
    if connection.vendor != "postgresql":
        return [f"{alias} 데이터베이스가 PostgreSQL이 아닙니다."]

    errors = []
    with connection.cursor() as cursor:
        for model in business_models():
            pk = model._meta.pk
            if not isinstance(
                pk,
                (models.AutoField, models.BigAutoField, models.SmallAutoField),
            ):
                continue
            max_pk = (
                model._default_manager.using(alias).aggregate(value=Max(pk.name))[
                    "value"
                ]
                or 0
            )
            cursor.execute(
                "SELECT pg_get_serial_sequence(%s, %s)",
                [model._meta.db_table, pk.column],
            )
            sequence_name = cursor.fetchone()[0]
            if not sequence_name:
                errors.append(f"{model._meta.label}: sequence를 찾을 수 없습니다.")
                continue
            quoted_sequence = ".".join(
                connection.ops.quote_name(part.strip('"'))
                for part in sequence_name.split(".")
            )
            cursor.execute(f"SELECT last_value, is_called FROM {quoted_sequence}")
            last_value, is_called = cursor.fetchone()
            next_value = last_value + 1 if is_called else last_value
            if next_value <= max_pk:
                errors.append(
                    f"{model._meta.label}: 다음 sequence 값 {next_value}가 최대 PK {max_pk} 이하입니다."
                )
    return errors


def constraint_errors(alias):
    connection = connections[alias]
    try:
        with transaction.atomic(using=alias):
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    except Exception as error:
        return [f"{alias} 제약조건 검사 실패: {error}"]
    return []


def identity_errors(source_alias, target_alias):
    user_model = apps.get_model("accounts", "User")
    feedback_thread_model = apps.get_model("chat", "FeedbackThread")
    errors = []
    for alias in (source_alias, target_alias):
        if not user_model._default_manager.using(alias).filter(pk=1).exists():
            errors.append(f"{alias}: 개발자 사용자 PK 1이 없습니다.")
        invalid_developer_ids = list(
            feedback_thread_model._default_manager.using(alias)
            .exclude(developer_id=1)
            .values_list("developer_id", flat=True)
            .distinct()
        )
        if invalid_developer_ids:
            errors.append(
                f"{alias}: developer_id가 1이 아닌 피드백 thread가 있습니다."
            )
    return errors


def media_errors(alias):
    media_root = Path(settings.MEDIA_ROOT)
    errors = []
    reference_count = 0
    for model in business_models():
        file_fields = [
            field
            for field in model._meta.concrete_fields
            if isinstance(field, models.FileField)
        ]
        if not file_fields:
            continue
        queryset = model._default_manager.using(alias).only(
            model._meta.pk.name,
            *(field.name for field in file_fields),
        )
        for instance in queryset:
            for field in file_fields:
                value = getattr(instance, field.name)
                if not value:
                    continue
                reference_count += 1
                if not (media_root / value.name).is_file():
                    errors.append(
                        f"{model._meta.label} PK {instance.pk}: 미디어 파일이 없습니다."
                    )
    return reference_count, errors
