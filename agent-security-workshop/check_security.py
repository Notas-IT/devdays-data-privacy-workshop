"""Start the workshop and run all repeatable live-container security checks."""

from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    started = subprocess.run(
        ['docker', 'compose', '-f', str(root / 'docker-compose.yml'),
         'up', '-d', '--build', '--wait'],
    )
    if started.returncode:
        return started.returncode
    result = subprocess.run(
        [sys.executable, '-m', 'unittest', 'discover', '-s', str(root / 'tests'), '-v'],
    )
    if result.returncode == 0:
        print('PASS: all agent security checks passed.', flush=True)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
