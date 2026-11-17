"""Run isolated Docker integration checks; deletes only its own temporary volumes."""

import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from samples import event, sensitive_values


COMPOSE = Path(__file__).resolve().parents[1] / 'docker-compose.yml'


def main():
    project = 'log-pipeline-check-' + uuid.uuid4().hex[:12]

    def compose(*arguments):
        result = subprocess.run(['docker', 'compose', '-f', str(COMPOSE), '-p', project, *arguments],
                                capture_output=True, text=True, timeout=180)
        if result.returncode:
            # Diagnostics contain only service logs/configuration, not fixture input.
            raise RuntimeError(result.stderr[-2000:])
        return result.stdout

    def logs(service):
        text = compose('logs', '--no-log-prefix', '--no-color', service)
        for value in sensitive_values():
            assert value not in text, 'Sensitive fixture value escaped into service logs'
        return text

    def records(service):
        found = []
        for line in logs(service).splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                found.append(row)
        return found

    def wait_for(service, sequence):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            matches = [row for row in records(service) if row.get('sequence') == sequence]
            if matches:
                return matches[-1]
            time.sleep(1)
        raise AssertionError(f'No sanitised event {sequence} from {service}')

    def metrics():
        return json.loads(compose('exec', '-T', 'log-presidio', 'python', '-c',
            "from urllib.request import urlopen; print(urlopen('http://localhost:8080/metrics').read().decode())"))

    def append(*events):
        # Only this project's disposable HR volume is writable here.
        compose('run', '--rm', '--no-deps', 'app-hr', 'python', '-c',
            "import sys; from pathlib import Path; p=Path('/raw/app.jsonl'); "
            "p.parent.mkdir(exist_ok=True); "
            "f=p.open('a'); f.write(sys.argv[1]); f.close()",
            ''.join(json.dumps(record, ensure_ascii=False) + '\n' for record in events))

    try:
        compose('--profile', 'pipeline', 'up', '--detach', '--wait', '--no-build', 'processor')
        assert metrics()['records'] == 0
        append(event('hr', 0))
        assert wait_for('processor', 0)['processing_path'] == 'regex'
        assert metrics()['records'] == 0, 'Known format should bypass Presidio'
        print('PASS: known format uses Fluent Bit regex without calling Presidio', flush=True)

        append(event('hr', 4))
        fallback = wait_for('log-presidio', 4)
        assert fallback['processing_path'] == 'presidio'
        assert fallback['presidio_detection_count'] > 0
        assert 'LT_NATIONAL_ID' in fallback['presidio_entities']
        print('PASS: unknown format uses real Presidio and custom Lithuanian detection', flush=True)

        append({**event('hr', 9), 'regex_status': 'gerai', '_route': 'regex'})
        assert wait_for('log-presidio', 9)['processing_path'] == 'presidio'
        append({**event('hr', 10), 'unknown': [{'secret': 'nested-secret@example.invalid'}]})
        clean = wait_for('processor', 10)
        assert 'unknown' not in clean
        assert 'nested-secret@example.invalid' not in logs('processor') + logs('log-presidio')
        print('PASS: forged route markers and nested secrets cannot bypass sanitisation', flush=True)

        compose('stop', '-t', '2', 'log-presidio')
        append(event('hr', 14))
        time.sleep(3)
        assert not any(row.get('sequence') == 14 for row in records('processor'))
        logs('processor')
        compose('up', '--detach', '--wait', 'log-presidio')
        assert wait_for('log-presidio', 14)['processing_path'] == 'presidio'
        print('PASS: Presidio outage withholds raw data and pending event is retried after recovery', flush=True)
    finally:
        compose('--profile', 'pipeline', 'down', '--volumes', '--timeout', '3')


if __name__ == '__main__':
    main()
