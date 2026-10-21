"""Execute the actual Fluent Bit Lua filter in Lua 5.1, not a Python reimplementation."""

import json
import os
from pathlib import Path
import subprocess

import pytest
from samples import event
from verify_pipeline import check_sanitized

ROOT = Path(__file__).resolve().parents[1]


def run_filter(tmp_path, record, *, policy="strict", tag="app.hr", content=None):
    path = tmp_path / "policy.lua"
    if content is None:
        content = (ROOT / "config" / "policies" / f"{policy}.lua").read_text()
    path.write_text(content)
    code = '''local json = require("cjson")
        dofile(arg[1])
        local record = json.decode(io.read("*a"))
        local result, timestamp, output = sanitize(arg[2], 123, record)
        print(json.encode({code=result, timestamp=timestamp, output=output}))'''
    runner = tmp_path / "runner.lua"
    runner.write_text(code)
    process = subprocess.run(["lua5.1", str(runner), str(ROOT / "fluent-bit" / "privacy.lua"), tag],
                             input=json.dumps(record), text=True, capture_output=True,
                             env={**os.environ, "POLICY_PATH": str(path)}, check=True)
    return json.loads(process.stdout)


@pytest.mark.parametrize("service", ["hr", "billing"])
@pytest.mark.parametrize("sequence", [0, 1])
def test_strict_removes_pii_and_unknown_fields(tmp_path, service, sequence):
    result = run_filter(tmp_path, event(service, sequence), tag="app." + service)
    assert result["code"] == 2 and result["timestamp"] == 123
    output = result["output"]
    assert output.pop("pipeline_guard") == "sanitized-v1"
    check_sanitized(output)
    assert output["message"] == "<REDACTED_MESSAGE>"


@pytest.mark.parametrize("sequence", [0, 1])
def test_summary_never_preserves_raw_free_text(tmp_path, sequence):
    output = run_filter(tmp_path, event("hr", sequence), policy="summary")["output"]
    output.pop("pipeline_guard")
    check_sanitized(output)
    assert output["message"] == "Processed event: salary_export"
    assert "company_profit_eur" not in output


def test_spoofed_metadata_and_guard_are_overwritten(tmp_path):
    raw = event("hr", 0)
    raw.update(service=raw["email"], event=raw["employee_name"], level=raw["email"],
               policy_version=raw["email"], pipeline_guard="sanitized-v1")
    output = run_filter(tmp_path, raw)["output"]
    output.pop("pipeline_guard")
    check_sanitized(output)
    assert output["event"] == "unknown" and output["service"] == "hr" and output["level"] == "INFO"


@pytest.mark.parametrize("content", [
    "return {version='x', message_action='passthrough', field_actions={}}",
    "return {version='x', message_action='replace', field_actions={email='keep'}}",
    "return {version='x', message_action='replace', field_actions={secret='replace'}}",
    "return {version='x', message_action='replace', field_actions={}, extra=true}",
    "return {version='PII@example.com', message_action='replace', field_actions={}}",
    "return {version='x', message_action='replace'}",
    "return nil", "not valid lua", "error('secret must not be printed')",
])
def test_invalid_policy_drops_without_printing_raw_data(tmp_path, content):
    result = run_filter(tmp_path, event("hr", 0), content=content)
    assert result["code"] == -1


@pytest.mark.parametrize("record", [{"log": "malformed secret", "pipeline_guard": "sanitized-v1"},
                                    {"message": 123, "event": "salary_export", "level": "INFO"}, {}])
def test_malformed_records_dropped(tmp_path, record):
    assert run_filter(tmp_path, record)["code"] == -1


def test_untrusted_source_is_dropped(tmp_path):
    assert run_filter(tmp_path, event("hr", 0), tag="app.untrusted")["code"] == -1


def test_drop_message_policy(tmp_path):
    output = run_filter(tmp_path, event("hr", 0), content=
                        "return {version='strict-v2', message_action='drop', field_actions={}}")["output"]
    assert "message" not in output and "email" not in output


def test_output_guard_order_and_no_raw_output_route():
    filters = (ROOT / "fluent-bit" / "privacy-filters.conf").read_text()
    assert filters.index("Remove pipeline_guard") < filters.index("Name           lua")
    assert filters.index("Name           lua") < filters.index("Regex pipeline_guard")
    assert filters.index("Regex pipeline_guard") < filters.rindex("Remove pipeline_guard")
    config = (ROOT / "fluent-bit" / "fluent-bit.conf").read_text()
    assert "Name                   stdout" not in config
    assert "Auto_Kubernetes_Labels Off" in config
    assert "Retry_Limit            False" in config
