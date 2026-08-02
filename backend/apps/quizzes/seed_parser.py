import json
import re
from pathlib import Path


QUESTION_PATTERN = re.compile(r"^(\d+)\. (.+)$")


def parse_quiz_markdown(source_path):
    source_path = Path(source_path)
    text = source_path.read_text(encoding="utf-8")
    if "\ufffd" in text:
        raise ValueError("UTF-8 대체문자가 포함되어 있습니다.")

    category = None
    questions = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line or raw_line == "---":
            continue
        if raw_line.startswith("### "):
            category = raw_line[4:]
            if not category:
                raise ValueError(f"{line_number}행의 분류가 비어 있습니다.")
            continue
        match = QUESTION_PATTERN.match(raw_line)
        if not match:
            raise ValueError(f"{line_number}행을 해석할 수 없습니다: {raw_line}")
        if category is None:
            category = "미분류"
        number = int(match.group(1))
        body = match.group(2)
        questions.append(
            {
                "stable_id": f"SYSTEM_{number:03d}",
                "original_number": number,
                "category": category,
                "body": body,
                "is_active": True,
                "display_order": len(questions) + 1,
            }
        )

    if not questions:
        raise ValueError("질문이 없습니다.")
    numbers = [question["original_number"] for question in questions]
    if len(numbers) != len(set(numbers)):
        raise ValueError("원본 번호가 중복되었습니다.")
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError("원본 번호는 1부터 연속되어야 합니다.")
    stable_ids = [question["stable_id"] for question in questions]
    if len(stable_ids) != len(set(stable_ids)):
        raise ValueError("질문 ID가 중복되었습니다.")
    return questions


def write_seed_json(questions, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "category_count": len({question["category"] for question in questions}),
            "question_count": len(questions),
        },
        "questions": questions,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_seed_json(seed_path):
    seed_path = Path(seed_path)
    text = seed_path.read_text(encoding="utf-8")
    if "\ufffd" in text:
        raise ValueError("시드 파일에 UTF-8 대체문자가 포함되어 있습니다.")
    payload = json.loads(text)
    questions = payload.get("questions", [])
    if payload.get("metadata", {}).get("question_count") != len(questions):
        raise ValueError("시드 메타데이터의 질문 수가 일치하지 않습니다.")
    if payload.get("metadata", {}).get("category_count") != len(
        {question["category"] for question in questions}
    ):
        raise ValueError("시드 메타데이터의 분류 수가 일치하지 않습니다.")
    return questions
