"""One unchanged acceptance contract for default and customized detection."""

import json
from pathlib import Path
from detector import detect, redact

FIXTURES = Path(__file__).parent / "examples" / "lithuanian_logs.jsonl"


def load_examples():
    with FIXTURES.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def validate_case(analyzer, case):
    results = detect(analyzer, case["text"])
    sanitized = redact(analyzer, case["text"])
    errors = []
    for expected in case["expected"]:
        if case["text"][expected["start"]:expected["end"]] != expected["value"]:
            raise ValueError(f"Invalid fixture span: {case['id']}")
        # Partial detections do not count: the entire annotated value must match.
        if not any(result.entity_type == expected["entity"]
                   and result.start == expected["start"]
                   and result.end == expected["end"] for result in results):
            errors.append(f"missing full {expected['entity']} span at {expected['start']}:{expected['end']}")
        if expected["value"] in sanitized:
            errors.append(f"{expected['entity']} still visible after redaction")
    for entity in case["forbidden_entities"]:
        if any(result.entity_type == entity for result in results):
            errors.append(f"false positive: {entity}")
    return errors


def assert_case(analyzer, case):
    errors = validate_case(analyzer, case)
    assert not errors, f"{case['id']}: " + "; ".join(errors)
