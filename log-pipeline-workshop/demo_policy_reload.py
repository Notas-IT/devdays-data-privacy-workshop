"""Live Fluent Bit policy switching and fail-closed drop demonstration."""

from pathlib import Path
import time
from urllib.error import URLError
from set_policy import activate
from verify_pipeline import check_sanitized, output_count, query_logs
import json


def wait_for(predicate):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except (OSError, URLError):
            pass
        time.sleep(1)
    raise AssertionError("Fluent Bit did not reach the expected state within 45 seconds")


def main():
    active = Path(__file__).parent / "config" / "active.lua"
    original = active.read_bytes()
    try:
        start = time.time_ns()
        activate("summary")
        streams = wait_for(lambda: query_logs(start, "summary-v1"))
        for stream in streams:
            for _, line in stream["values"]:
                record = json.loads(line)
                check_sanitized(record)
                assert record["message"].startswith("Processed event:")
                assert "company_profit_eur" not in record
        print("PASS: Fluent Bit switched to a safe event-summary policy without restarting")
        activate("invalid")
        # Drain any already-sanitized batches queued before the policy change.
        time.sleep(5)
        before = output_count()
        files = ("/raw/hr/app.jsonl", "/raw/billing/app.jsonl")
        sizes = [Path(filename).stat().st_size for filename in files]
        start = time.time_ns()
        time.sleep(5)
        assert output_count() == before, "Invalid policy allowed forwarding"
        assert not query_logs(start), "Logs escaped while the policy was invalid"
        assert all(Path(filename).stat().st_size > size for filename, size in zip(files, sizes))
        print("PASS: invalid policy dropped new records; raw application logs kept growing")
    finally:
        temporary = active.with_suffix(".tmp")
        temporary.write_bytes(original)
        temporary.replace(active)
    start = time.time_ns()
    wait_for(lambda: query_logs(start))
    print("PASS: original policy restored; new records resumed (dropped records are not replayed)")


if __name__ == "__main__":
    main()
