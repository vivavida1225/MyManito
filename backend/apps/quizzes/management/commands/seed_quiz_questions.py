from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.quizzes.models import SystemQuizQuestion
from apps.quizzes.seed_parser import load_seed_json


class Command(BaseCommand):
    help = "추적된 JSON 시드를 시스템 퀴즈 질문에 멱등 반영합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--seed",
            default=str(Path(settings.BASE_DIR) / "apps" / "quizzes" / "data" / "system_questions.json"),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        questions = load_seed_json(options["seed"])
        stable_ids = []
        for question in questions:
            stable_ids.append(question["stable_id"])
            SystemQuizQuestion.objects.update_or_create(
                stable_id=question["stable_id"],
                defaults={
                    "original_number": question["original_number"],
                    "category": question["category"],
                    "body": question["body"],
                    "is_active": question.get("is_active", True),
                    "display_order": question["display_order"],
                },
            )
        SystemQuizQuestion.objects.exclude(stable_id__in=stable_ids).update(is_active=False)
        self.stdout.write(self.style.SUCCESS(f"{len(questions)}개 시스템 질문을 반영했습니다."))
