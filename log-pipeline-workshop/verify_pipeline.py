"""Check raw PII at the source and its absence in recent Loki log content."""

import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError
from policy import FIELDS, SOURCES
from samples import sensitive_values


def check_sanitized(record):
    allowed = FIELDS | {"service", "level", "event", "policy_version", "policy_revision", "message"}
    if set(record) - allowed:
        raise AssertionError("Unapproved fields reached Loki")
    for field in FIELDS & record.keys():
        if record[field] != "<REDACTED>":
            raise AssertionError(f"Raw value survived in {field}")
    for key, value in record.items():
        if key == "policy_revision":
            continue
        if isinstance(value, str) and any(marker in value for marker in sensitive_values()):
            raise AssertionError(f"Synthetic sensitive value survived in {key}")


def get_json(url):
    with urlopen(url, timeout=5) as response:
        return json.load(response)


def main():
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            status = get_json("http://log-processor:8080/status")
            if not status["ready"]:
                time.sleep(1)
                continue
            query = urlencode({"query": '{workshop="log-pipeline"}',
                               "start": str(time.time_ns() - 300 * 10**9), "limit": 1000})
            response = get_json("http://log-loki:3100/loki/api/v1/query_range?" + query)
            streams = response["data"]["result"]
            services = {stream["stream"]["service"] for stream in streams}
            if services != set(SOURCES):
                time.sleep(1)
                continue
            count = 0
            for stream in streams:
                labels = stream["stream"]
                required = {"workshop", "namespace", "service"}
                assert required <= set(labels) <= required | {"service_name", "detected_level"}, "Unapproved Loki labels"
                assert labels["workshop"] == "log-pipeline" and labels["namespace"] == "privacy-demo"
                if "service_name" in labels:
                    assert labels["service_name"] == labels["service"], "Unexpected inferred service"
                if "detected_level" in labels:
                    assert labels["detected_level"] in {"info", "warn", "error", "unknown"}, "Unexpected inferred severity"
                for _, line in stream["values"]:
                    record = json.loads(line)
                    assert record["service"] == labels["service"]
                    check_sanitized(record)
                    count += 1
            for filename in SOURCES.values():
                source = Path(filename).read_text(encoding="utf-8")
                assert any(marker in source for marker in sensitive_values()), "Raw source unexpectedly sanitized"
            print(f"PASS: raw PII remains in both simulated pods; {count} recent Loki entries contain no sample PII")
            print(f"Active policy: {status['policy_version']}; only allowlisted labels and fields reached Loki")
            return 0
        except (OSError, URLError, KeyError):
            time.sleep(1)
    raise SystemExit("FAIL: pipeline was not ready with logs from both applications within 45 seconds")


if __name__ == "__main__":
    raise SystemExit(main())
