import pytest
from detector import detect
from validation import FIXTURES, assert_case, load_examples, validate_case
from generate_examples import generate_examples


@pytest.mark.parametrize("case", load_examples(), ids=lambda case: case["id"])
def test_lithuanian_detection_and_redaction(lithuanian_analyzer, case):
    assert_case(lithuanian_analyzer, case)


def test_generated_fixtures_are_reproducible():
    assert load_examples() == generate_examples()
    assert FIXTURES.with_suffix(".log").read_text(encoding="utf-8").splitlines() == [
        case["text"] for case in generate_examples()
    ]


def test_default_email_control(default_analyzer):
    case = next(case for case in load_examples() if case["id"] == "standard_email")
    assert_case(default_analyzer, case)


def test_baseline_has_real_blind_spots(default_analyzer):
    cases = {case["id"]: case for case in load_examples()}
    for case_id in ["personal_code", "obfuscated_email", "salary"]:
        assert validate_case(default_analyzer, cases[case_id]), case_id


def test_service_filter_preserves_adjacent_person(lithuanian_analyzer):
    case = next(case for case in load_examples() if case["id"] == "service_and_person")
    people = [result for result in detect(lithuanian_analyzer, case["text"])
              if result.entity_type == "PERSON"]
    assert [(result.start, result.end) for result in people] == [
        (case["expected"][0]["start"], case["expected"][0]["end"])
    ]


def test_event_word_in_person_field_is_not_suppressed(lithuanian_analyzer):
    text = "2026-10-14T09:00:00Z INFO Patikra: darbuotojas=Patikra Žukauskas; būsena=gerai"
    people = [result for result in detect(lithuanian_analyzer, text)
              if result.entity_type == "PERSON"]
    assert [text[result.start:result.end] for result in people] == ["Patikra Žukauskas"]
