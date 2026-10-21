"""Check real Fluent Bit delivery, raw source PII, and sanitized Loki output."""

import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError
from samples import sensitive_values

FIELDS = {"employee_name", "national_id", "email", "phone", "address", "salary_eur", "company_profit_eur"}
SOURCES = {"hr": "/raw/hr/app.jsonl", "billing": "/raw/billing/app.jsonl"}
METRICS = "http://log-processor:8080/api/v1/metrics"


def check_sanitized(record):
    allowed = FIELDS | {"service", "level", "event", "policy_version", "message"}
    assert not set(record) - allowed, "Unapproved fields reached Loki"
    for field in FIELDS & record.keys():
        assert record[field] == "<REDACTED>", f"Raw value survived in {field}"
    assert record["service"] in SOURCES
    assert record["level"] in {"INFO", "WARN", "ERROR", "DEBUG"}
    assert record["event"] in {"salary_export", "invoice_created", "unknown"}
    assert record["policy_version"] in {"strict-v2", "summary-v1"}
    if "message" in record:
        assert record["message"] in {"<REDACTED_MESSAGE>", "Processed event: salary_export",
                                      "Processed event: invoice_created", "Processed event: unknown"}
    assert not any(marker in json.dumps(record, ensure_ascii=False) for marker in sensitive_values())


def get_json(url):
    with urlopen(url, timeout=5) as response:
        return json.load(response)


def query_logs(start=None, policy=None):
    query = '{workshop="log-pipeline",collector="fluent-bit"}'
    if policy:
        query += ' | json | policy_version="' + policy + '"'
    parameters = {"query": query, "start": str(start or time.time_ns() - 60 * 10**9), "limit": 1000}
    return get_json("http://log-loki:3100/loki/api/v1/query_range?" + urlencode(parameters))["data"]["result"]


def output_count():
    metrics = get_json(METRICS)
    return sum(item.get("proc_records", 0) for item in metrics.get("output", {}).values())


def main():
    deadline = time.monotonic() + 45
    # Require fresh records, not historical records left by a stopped collector.
    start = time.time_ns()
    while time.monotonic() < deadline:
        try:
            metrics = get_json(METRICS)
            assert metrics.get("input") and metrics.get("output"), "Missing collector metrics"
            streams = query_logs(start)
            if {stream["stream"]["service"] for stream in streams} != set(SOURCES):
                time.sleep(1)
                continue
            count = 0
            for stream in streams:
                labels = stream["stream"]
                required = {"workshop", "namespace", "service", "collector"}
                assert required <= set(labels) <= required | {"service_name", "detected_level"}, "Unapproved Loki labels"
                assert labels["namespace"] == "privacy-demo" and labels["collector"] == "fluent-bit"
                if "service_name" in labels:
                    assert labels["service_name"] == labels["service"]
                if "detected_level" in labels:
                    assert labels["detected_level"] in {"info", "warn", "error", "debug", "unknown"}
                for _, line in stream["values"]:
                    record = json.loads(line)
                    assert record["service"] == labels["service"]
                    check_sanitized(record)
                    count += 1
            for filename in SOURCES.values():
                with Path(filename).open(encoding="utf-8") as source:
                    head = source.read(16384)
                assert any(marker in head for marker in sensitive_values()), "Raw source unexpectedly sanitized"
            print(f"PASS: Fluent Bit sent {count} fresh sanitized entries from both applications to Loki")
            print("PASS: raw PII remains at the source; only approved fields and labels reached Loki")
            return 0
        except (OSError, URLError, KeyError):
            time.sleep(1)
    raise SystemExit("FAIL: no fresh Fluent Bit logs from both applications within 45 seconds")


if __name__ == "__main__":
    raise SystemExit(main())
