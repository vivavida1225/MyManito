from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.quizzes.seed_parser import parse_quiz_markdown, write_seed_json


class Command(BaseCommand):
    help = "tmp/quizes_raw.md를 추적 가능한 UTF-8 JSON 시드로 변환합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=str(Path(settings.BASE_DIR).parent / "tmp" / "quizes_raw.md"),
        )
        parser.add_argument(
            "--output",
            default=str(Path(settings.BASE_DIR) / "apps" / "quizzes" / "data" / "system_questions.json"),
        )

    def handle(self, *args, **options):
        questions = parse_quiz_markdown(options["source"])
        write_seed_json(questions, options["output"])
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(questions)}개 질문을 UTF-8 시드로 생성했습니다: {options['output']}"
            )
        )

