"""Tail simulated pod logs, sanitize before egress, then push to Loki."""

import json
import os
from pathlib import Path
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import URLError

from policy import PolicyStore, SOURCES, sanitize


def push(loki_url, service, record):
    payload = {"streams": [{
        "stream": {"workshop": "log-pipeline", "namespace": "privacy-demo", "service": service},
        "values": [[str(time.time_ns()), json.dumps(record, ensure_ascii=False)]],
    }]}
    request = Request(loki_url + "/loki/api/v1/push", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5) as response:
        if response.status != 204:
            raise OSError("Loki did not confirm ingestion")


class Processor:
    def __init__(self, policy_path, state_path, loki_url):
        self.store = PolicyStore(policy_path)
        self.state_path = state_path
        self.loki_url = loki_url
        self.analyzer = None
        self.ready = False
        self.counters = {"forwarded": 0, "invalid_records": 0, "delivery_errors": 0}
        self.offsets = json.loads(state_path.read_text()) if state_path.exists() else {}

    def status(self):
        return {"policy_valid": self.store.valid, "ready": self.ready,
                "policy_version": self.store.policy["version"] if self.store.valid else None,
                "policy_revision": self.store.revision if self.store.valid else None,
                **self.counters}

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.offsets), encoding="utf-8")
        temporary.replace(self.state_path)

    def cycle(self):
        self.ready = False
        if not self.store.refresh():
            return
        if self.store.policy["message_action"] == "presidio" and self.analyzer is None:
            from shared_detector import build_analyzer
            self.analyzer = build_analyzer("lithuanian")
        # Loki readiness matters before consuming any source records.
        with urlopen(self.loki_url + "/ready", timeout=3):
            pass
        self.ready = True
        for service, filename in SOURCES.items():
            path = Path(filename)
            if not path.exists():
                continue
            with path.open("rb") as source:
                info = os.fstat(source.fileno())
                checkpoint = self.offsets.get(service, {})
                offset = checkpoint.get("offset", 0)
                if checkpoint.get("inode") != info.st_ino or info.st_size < offset:
                    offset = 0
                source.seek(offset)
                for _ in range(100):
                    line = source.readline()
                    if not line or not line.endswith(b"\n"):
                        break
                    try:
                        record = json.loads(line)
                        sanitized = sanitize(record, service, self.store.policy,
                                             self.store.revision, self.analyzer)
                    except (ValueError, TypeError, UnicodeError):
                        self.counters["invalid_records"] += 1
                    else:
                        # Checkpoint is advanced only after confirmed sanitized delivery.
                        push(self.loki_url, service, sanitized)
                        self.counters["forwarded"] += 1
                    self.offsets[service] = {"inode": info.st_ino, "offset": source.tell()}
                    self.save()


def main():
    processor = Processor(Path(os.environ.get("POLICY_PATH", "/config/active.json")),
                          Path("/state/checkpoints.json"), os.environ.get("LOKI_URL", "http://log-loki:3100"))
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())

    class StatusHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in {"/health", "/status"}:
                self.send_error(404)
                return
            status = processor.status()
            code = 503 if self.path == "/health" and not status["ready"] else 200
            body = json.dumps(status).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", 8080), StatusHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Log processor started; raw records are never printed", flush=True)
    previous = None
    while not stopped.is_set():
        try:
            processor.cycle()
        except (OSError, URLError, ValueError):
            processor.ready = False
            processor.counters["delivery_errors"] += 1
        state = (processor.store.valid, processor.ready, processor.store.revision)
        if state != previous:
            print(json.dumps(processor.status()), flush=True)
            previous = state
        stopped.wait(1)
    server.shutdown()
    server.server_close()


if __name__ == "__main__":
    main()
