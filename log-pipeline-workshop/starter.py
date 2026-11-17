"""Process one bounded batch, emitting only approved operational metadata.

Free-text messages are replaced wholesale. Other payload fields are omitted,
including nested objects and arrays; no fixture-specific PII list is needed.
"""

from contextlib import ExitStack
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys


INPUTS = (('hr', Path('/raw/hr/app.jsonl')), ('billing', Path('/raw/billing/app.jsonl')))
MAX_RECORD_BYTES = 1024 * 1024
LEVELS = {'TRACE', 'DEBUG', 'INFO', 'WARN', 'WARNING', 'ERROR', 'CRITICAL', 'FATAL'}
EVENT_NAME = re.compile(r'[a-z][a-z_]{0,63}\Z')


def sanitise(record, service):
    """Allowlist metadata; treat unapproved payloads as sensitive by default."""
    result = {'source_service': service}
    level = record.get('level')
    if isinstance(level, str) and level.upper() in LEVELS:
        result['level'] = level.upper()
    event = record.get('event')
    if isinstance(event, str) and EVENT_NAME.fullmatch(event):
        result['event'] = event
    sequence = record.get('sequence')
    if type(sequence) is int and 0 <= sequence <= 2**63 - 1:
        result['sequence'] = sequence
    timestamp = record.get('timestamp')
    if isinstance(timestamp, str) and len(timestamp) <= 64:
        try:
            result['timestamp'] = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).isoformat()
        except ValueError:
            pass
    if 'message' in record:
        result['message'] = '[REDACTED]'
    return result


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def invalid_constant(_):
    raise ValueError('Nonstandard JSON constant')


def process_snapshot(stream, size, service, output, errors):
    """Read at most the initial byte count, keeping appending writers out of this batch."""
    remaining, line_number = size, 0
    while remaining > 0:
        line = stream.readline(min(remaining, MAX_RECORD_BYTES + 1))
        if not line:
            break
        remaining -= len(line)
        line_number += 1
        if len(line) > MAX_RECORD_BYTES:
            # Drain just this oversized record, bounded by the original snapshot.
            while remaining and not line.endswith(b'\n'):
                line = stream.readline(min(remaining, MAX_RECORD_BYTES))
                if not line:
                    break
                remaining -= len(line)
            print(f'{service}: skipped oversized record at line {line_number}', file=errors)
            continue
        try:
            record = json.loads(line.decode('utf-8'), object_pairs_hook=unique_fields,
                                parse_constant=invalid_constant)
            if not isinstance(record, dict):
                raise ValueError('Expected a JSON object')
            clean = sanitise(record, service)
        except (ValueError, UnicodeError, RecursionError):
            # Do not echo source content, keys or parser exception messages.
            print(f'{service}: skipped malformed record at line {line_number}', file=errors)
            continue
        print(json.dumps(clean, ensure_ascii=False, allow_nan=False), file=output, flush=True)


def run_batch(inputs=INPUTS, output=None, errors=None):
    output = sys.stdout if output is None else output
    errors = sys.stderr if errors is None else errors
    failed = False
    with ExitStack() as stack:
        snapshots = []
        # Capture both file sizes before processing either source.
        for service, path in inputs:
            try:
                stream = stack.enter_context(Path(path).open('rb'))
                snapshots.append((stream, os.fstat(stream.fileno()).st_size, service))
            except OSError:
                print(f'{service}: input unavailable', file=errors)
                failed = True
        for stream, size, service in snapshots:
            try:
                process_snapshot(stream, size, service, output, errors)
            except OSError:
                print(f'{service}: input/output failure', file=errors)
                failed = True
    return int(failed)


def main():
    return run_batch()


if __name__ == "__main__":
    raise SystemExit(main())
