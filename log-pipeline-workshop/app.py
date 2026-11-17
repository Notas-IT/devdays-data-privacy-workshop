"""Simulated pod: append raw JSON logs to its volume and its stdout."""

import json
import math
import os
from pathlib import Path
import signal
import threading
from samples import event


def main():
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    service = os.environ.get("APP_SERVICE", "hr")
    if service not in {"hr", "billing"}:
        raise ValueError("Unknown simulated application")
    interval = float(os.environ.get("LOG_INTERVAL_SECONDS", "2"))
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("LOG_INTERVAL_SECONDS must be a positive number")
    directory = Path("/raw")
    directory.mkdir(parents=True, exist_ok=True)
    sequence = 0
    with (directory / "app.jsonl").open("a", encoding="utf-8", buffering=1) as output:
        while not stopped.is_set():
            line = json.dumps(event(service, sequence), ensure_ascii=False)
            output.write(line + "\n")
            print(line, flush=True)
            sequence += 1
            stopped.wait(interval)


if __name__ == "__main__":
    main()
