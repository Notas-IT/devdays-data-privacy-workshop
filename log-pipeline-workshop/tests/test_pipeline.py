import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import policy
import processor
from policy import PolicyStore, sanitize, validate_policy
from samples import event
from verify_pipeline import check_sanitized

ROOT = Path(__file__).resolve().parents[1]


def config(name):
    return json.loads((ROOT / "config" / "policies" / f"{name}.json").read_text())


@pytest.mark.parametrize("service", ["hr", "billing"])
@pytest.mark.parametrize("sequence", [0, 1])
def test_strict_policy_removes_all_sample_pii(service, sequence):
    output = sanitize(event(service, sequence), service, config("strict"), "publichash")
    check_sanitized(output)
    assert output["message"] == "<REDACTED_MESSAGE>"
    assert "debug" not in output and "labels" not in output


@pytest.fixture(scope="module")
def analyzer():
    from shared_detector import build_analyzer
    return build_analyzer("lithuanian")


@pytest.mark.parametrize("sequence", [0, 1])
def test_presidio_policy_redacts_message_and_drops_profit(analyzer, sequence):
    output = sanitize(event("hr", sequence), "hr", config("presidio"), "publichash", analyzer)
    check_sanitized(output)
    assert "company_profit_eur" not in output
    assert "<LT_PERSON_CODE>" in output["message"] and "<EMAIL_ADDRESS>" in output["message"]


def test_unconfigured_fields_and_untrusted_metadata_are_not_forwarded():
    raw = event("hr", 0)
    raw.update({"event": raw["employee_name"], "level": raw["email"], "service": raw["email"]})
    rules = config("strict")
    rules["field_actions"] = {}
    output = sanitize(raw, "hr", rules, "publichash")
    check_sanitized(output)
    assert output["service"] == "hr" and output["level"] == "INFO" and output["event"] == "unknown"
    assert not policy.FIELDS & output.keys()


def test_invalid_policy_never_allows_passthrough():
    with pytest.raises(ValueError):
        validate_policy(config("invalid"))


def test_policy_recovers_when_same_valid_content_is_restored(tmp_path):
    path = tmp_path / "policy.json"
    content = json.dumps(config("strict"))
    path.write_text(content)
    store = PolicyStore(path)
    assert store.refresh()
    original_revision = store.revision
    path.write_text(json.dumps(config("invalid")))
    assert not store.refresh() and not store.valid
    path.write_text(content)
    assert store.refresh() and store.revision == original_revision


@pytest.fixture
def running_processor(tmp_path, monkeypatch):
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(config("strict")))
    log = tmp_path / "app.jsonl"
    monkeypatch.setattr(processor, "SOURCES", {"hr": str(log)})
    monkeypatch.setattr(processor, "urlopen", MagicMock())
    instance = processor.Processor(policy_path, tmp_path / "state.json", "http://test")
    return instance, log


def test_partial_line_is_not_consumed(running_processor, monkeypatch):
    instance, log = running_processor
    log.write_text(json.dumps(event("hr", 0)))
    sender = MagicMock()
    monkeypatch.setattr(processor, "push", sender)
    instance.cycle()
    assert instance.offsets == {} and not sender.called
    with log.open("a") as output:
        output.write("\n")
    instance.cycle()
    assert sender.call_count == 1


def test_delivery_failure_does_not_advance_checkpoint(running_processor, monkeypatch):
    instance, log = running_processor
    log.write_text(json.dumps(event("hr", 0)) + "\n")
    monkeypatch.setattr(processor, "push", MagicMock(side_effect=OSError("offline")))
    with pytest.raises(OSError):
        instance.cycle()
    assert instance.offsets == {} and not instance.state_path.exists()


def test_checkpoint_survives_restart(running_processor, monkeypatch):
    instance, log = running_processor
    log.write_text(json.dumps(event("hr", 0)) + "\n")
    sender = MagicMock()
    monkeypatch.setattr(processor, "push", sender)
    instance.cycle()
    resumed = processor.Processor(instance.store.path, instance.state_path, "http://test")
    resumed.cycle()
    assert sender.call_count == 1
    with log.open("a") as output:
        output.write(json.dumps(event("hr", 1)) + "\n")
    resumed.cycle()
    assert sender.call_count == 2


def test_invalid_policy_pauses_egress(running_processor, monkeypatch):
    instance, log = running_processor
    log.write_text(json.dumps(event("hr", 0)) + "\n")
    instance.store.path.write_text(json.dumps(config("invalid")))
    sender = MagicMock()
    monkeypatch.setattr(processor, "push", sender)
    instance.cycle()
    assert not instance.ready and instance.offsets == {} and not sender.called


def test_bad_record_is_not_forwarded_or_printed(running_processor, monkeypatch, capsys):
    instance, log = running_processor
    log.write_text("not-json-with-secret\n" + json.dumps(event("hr", 0)) + "\n")
    sender = MagicMock()
    monkeypatch.setattr(processor, "push", sender)
    instance.cycle()
    assert instance.counters["invalid_records"] == 1 and sender.call_count == 1
    assert "secret" not in capsys.readouterr().out


def test_push_has_only_safe_labels_and_sanitized_body(monkeypatch):
    captured = []
    response = MagicMock()
    response.__enter__.return_value.status = 204
    monkeypatch.setattr(processor, "urlopen", lambda request, **kwargs: captured.append(request) or response)
    sanitized = sanitize(event("hr", 0), "hr", config("strict"), "publichash")
    processor.push("http://test", "hr", sanitized)
    stream = json.loads(captured[0].data)["streams"][0]
    assert set(stream["stream"]) == {"workshop", "namespace", "service"}
    assert isinstance(stream["values"][0][0], str)
    check_sanitized(json.loads(stream["values"][0][1]))
