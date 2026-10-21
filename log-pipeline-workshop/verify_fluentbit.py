"""Run on the host: exercise the real Fluent Bit filter chain in isolated containers."""

import json
from pathlib import Path
import subprocess

from verify_pipeline import check_sanitized


def run(extra):
    result = subprocess.run(["docker", "compose", "run", "--rm", "--no-deps", *extra,
                             "fluentbit-filter-checks"], cwd=Path(__file__).resolve().parent,
                            text=True, capture_output=True, timeout=30, check=True)
    assert "native-secret@example.com" not in result.stdout + result.stderr, "Raw record escaped into collector output"
    records = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    for record in records:
        record.pop("date", None)  # stdout plugin's timestamp, not a source field
        check_sanitized(record)
    return records


def main():
    assert len(run([])) == 1, "Expected one sanitized record; malformed records must be dropped"
    print("PASS: native Fluent Bit chain sanitizes valid JSON and drops malformed/forged-marker records")
    assert not run(["-e", "PRIVACY_SCRIPT=/fluent-bit/tests/broken_filter.lua"]), "Lua failure forwarded a raw record"
    print("PASS: native Lua runtime failures cannot bypass the output guard, even with forged markers")


if __name__ == "__main__":
    main()
