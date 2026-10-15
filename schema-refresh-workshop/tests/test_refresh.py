from datetime import date
import json
import pytest

import classification
import refresh
from catalog import column_signature, validate_supported_schema
from clone import transform


def column(name="memo", type_name="text", nullable=True):
    return {"table_name": "people", "column_name": name, "type": type_name,
            "nullable": nullable, "default_hash": None, "identity": "", "generated": ""}


@pytest.fixture(scope="module", autouse=True)
def real_analyzer():
    classification.analyzer()


def test_email_tokens_preserve_cross_table_equality_and_uniqueness():
    rule = {"action": "token_email", "scope": "email"}
    first = transform("one@example.com", rule, b"test-key", "text")
    assert first == transform("one@example.com", rule, b"test-key", "text")
    assert first != transform("two@example.com", rule, b"test-key", "text")
    assert first.endswith("@example.invalid") and "one@example.com" not in first
    assert first != transform("one@example.com", rule, b"another-key", "text")


def test_date_and_null_transforms():
    assert transform(date(1990, 1, 1), {"action": "constant", "value": "2000-01-01"}, b"key", "date") == date(2000, 1, 1)
    assert transform(None, {"action": "token_id", "scope": "id"}, b"key", "text") is None
    assert transform("secret", {"action": "null"}, b"key", "text") is None


def test_email_detected_under_neutral_column_name(monkeypatch):
    monkeypatch.setattr(classification, "samples", lambda *_: ["hidden-person@example.com"])
    result = classification.classify(None, "people", column("extra"))
    assert result["decision"] == "anonymize" and result["rule"]["action"] == "null"
    assert result["entity_counts"]["EMAIL_ADDRESS"] >= 1
    assert "hidden-person" not in json.dumps(result)


def test_nested_json_data_is_sampled_and_flagged(monkeypatch):
    monkeypatch.setattr(classification, "samples", lambda *_: [json.dumps({"delivery": {"email": "delivery-secret@example.com"}})])
    result = classification.classify(None, "people", column("payload", "jsonb"))
    assert result["decision"] == "anonymize" and result["entity_counts"]["EMAIL_ADDRESS"] >= 1


def test_sensitive_name_is_flagged_even_with_no_samples(monkeypatch):
    monkeypatch.setattr(classification, "samples", lambda *_: [])
    assert classification.classify(None, "people", column("contact_email"))["decision"] == "anonymize"


def test_no_detections_does_not_approve_unknown_column(monkeypatch):
    monkeypatch.setattr(classification, "samples", lambda *_: [])
    assert classification.classify(None, "people", column("memo"))["decision"] == "review"


def test_sensitive_not_null_column_needs_review(monkeypatch):
    monkeypatch.setattr(classification, "samples", lambda *_: [])
    assert classification.classify(None, "people", column("contact_email", nullable=False))["decision"] == "review"


def test_benign_decision_requires_full_domain_check(monkeypatch):
    monkeypatch.setattr(classification, "samples", lambda *_: ["red"])
    monkeypatch.setattr(classification, "full_domain_is_safe", lambda *_: True)
    result = classification.classify(None, "people", column("favorite_color"))
    assert result["decision"] == "keep" and "domain" in result["rule"]
    monkeypatch.setattr(classification, "full_domain_is_safe", lambda *_: False)
    assert classification.classify(None, "people", column("favorite_color"))["decision"] != "keep"


def test_signature_detects_type_nullable_and_default_changes():
    original = column_signature(column())
    assert original != column_signature(column(type_name="jsonb"))
    assert original != column_signature(column(nullable=False))
    changed = column()
    changed["default_hash"] = "changed"
    assert original != column_signature(changed)


def test_unknown_types_are_blocked():
    with pytest.raises(ValueError):
        validate_supported_schema({"people": {"columns": [column(type_name="custom_domain")], "constraints": []}})


def test_existing_auto_approved_domain_is_rechecked(monkeypatch, tmp_path):
    monkeypatch.setattr(refresh, "STATE", tmp_path)
    tables = {"people": {"columns": [column("favorite_color")], "constraints": []}}
    policy = refresh.snapshot_policy(tables, {"people.favorite_color": {"action": "keep", "domain": ["red"]}})
    monkeypatch.setattr(refresh, "full_domain_is_safe", lambda *_: False)
    report, _ = refresh.analyze(None, tables, policy)
    assert not report["can_publish"] and "domain" in report["blockers"][0]


def test_changed_and_removed_columns_block_publication(monkeypatch, tmp_path):
    monkeypatch.setattr(refresh, "STATE", tmp_path)
    tables = {"people": {"columns": [column()], "constraints": []}}
    policy = refresh.snapshot_policy(tables, {"people.memo": {"action": "null"}})
    tables["people"]["columns"][0]["nullable"] = False
    report, _ = refresh.analyze(None, tables, policy)
    assert not report["can_publish"]
    tables["people"]["columns"] = []
    report, _ = refresh.analyze(None, tables, policy)
    assert "disappeared" in report["blockers"][0]
