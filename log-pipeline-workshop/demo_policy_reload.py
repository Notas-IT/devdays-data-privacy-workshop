"""Live test of policy reload, fail-closed forwarding, and backlog recovery."""

from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import json

from set_policy import activate
from verify_pipeline import check_sanitized, get_json

STATUS = "http://log-processor:8080/status"


def wait_for(predicate):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            status = get_json(STATUS)
            if predicate(status):
                return status
        except (OSError, URLError):
            pass
        time.sleep(0.5)
    raise AssertionError("Processor did not reach the expected state within 45 seconds")


def main():
    active = Path(__file__).parent / "config" / "active.json"
    original = active.read_bytes()
    original_version = json.loads(original)["version"]
    before = wait_for(lambda status: status["ready"])
    try:
        activate("presidio")
        wait_for(lambda status: status["ready"] and status["policy_version"] == "presidio-v1"
                 and status["forwarded"] >= before["forwarded"] + 6)
        query = urlencode({"query": '{workshop="log-pipeline"} | json | policy_version="presidio-v1"', "limit": 20})
        streams = get_json("http://log-loki:3100/loki/api/v1/query_range?" + query)["data"]["result"]
        assert streams, "No selectively redacted logs were stored"
        for stream in streams:
            for _, line in stream["values"]:
                record = json.loads(line)
                check_sanitized(record)
                assert "<LT_PERSON_CODE>" in record["message"]
        print("PASS: selective Presidio policy reloaded live and stored no sample PII")

        activate("invalid")
        paused = wait_for(lambda status: not status["policy_valid"] and not status["ready"])
        time.sleep(3)
        assert get_json(STATUS)["forwarded"] == paused["forwarded"], "Forwarding did not pause"
        try:
            with urlopen("http://log-processor:8080/health", timeout=3):
                pass
        except HTTPError as error:
            assert error.code == 503
        else:
            raise AssertionError("Invalid policy incorrectly passed the health check")
        print("PASS: invalid policy stopped forwarding and failed the readiness check")
    finally:
        temporary = active.with_suffix(".tmp")
        temporary.write_bytes(original)
        temporary.replace(active)
    wait_for(lambda status: status["ready"] and status["policy_version"] == original_version
             and status["forwarded"] >= paused["forwarded"] + 4)
    print("PASS: original policy restored and accumulated logs resumed forwarding")


if __name__ == "__main__":
    main()
