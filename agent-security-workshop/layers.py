"""Run independent cumulative stages; all Docker control stays on the presenter."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
STAGES = ['00-plain-database', '01-agent-process', '02-files', '03-host', '04-network',
          '05-database', '06-aggregates', '07-identity', '08-audit']


def level_for(value):
    if value in STAGES:
        return STAGES.index(value)
    try:
        level = int(value)
        if 0 <= level < len(STAGES):
            return level
    except ValueError:
        pass
    raise argparse.ArgumentTypeError('Choose 0 through 8, or a stage folder name')


def compose(level, *arguments, capture=False, data=None, timeout=600):
    practice = os.environ.get('AGENT_WORKSHOP_PRACTICE') == '1'
    folder = '.practice' if practice else 'layers'
    project = 'practice' if practice else 'layer'
    path = ROOT / folder / STAGES[level] / 'docker-compose.yml'
    if practice and not path.is_file():
        raise SystemExit(f'Prepare this exercise first: python3 agent-security-workshop/layers.py prepare {level}')
    command = ['docker', 'compose', '--project-name', f'devdays-agent-{project}-{level:02d}',
               '-f', str(path), *arguments]
    result = subprocess.run(command, text=True, input=data, capture_output=capture, timeout=timeout)
    if not capture and result.returncode:
        raise SystemExit(result.returncode)
    return result


def setup(level, action, **kwargs):
    return compose(level, 'run', '--rm', '--no-deps', '-T', 'setup', action, **kwargs)


def up(level, build=True):
    if build:
        compose(level, 'build', 'setup', 'agent')
    setup(level, 'secrets')
    compose(level, 'up', '-d', '--wait', 'db')
    setup(level, 'init')
    services = ['gateway', 'agent'] if level >= 4 else ['agent']
    compose(level, 'up', '-d', '--wait', *services)


def test(level):
    environment = {**os.environ, 'AGENT_WORKSHOP_STAGE': str(level)}
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'layer_runtime'),
                             '-p', 'test_stage.py', '-v'], env=environment)
    if result.returncode:
        raise SystemExit(result.returncode)


def prepare(level):
    if level == 0:
        raise SystemExit('Choose a layer from 1 to 8; stage 0 is the baseline.')
    destination = ROOT / '.practice' / STAGES[level]
    if destination.exists():
        raise SystemExit(f'Practice folder already exists; preserving your edits: {destination}')
    previous = ROOT / 'layers' / STAGES[level - 1]
    source = (previous / 'docker-compose.yml').read_text()
    source = source.replace(f'name: devdays-agent-layer-{level - 1:02d}',
                            f'name: devdays-agent-practice-{level:02d}')
    source = source.replace(f'STAGE_LEVEL: "{level - 1}"', f'STAGE_LEVEL: "{level}"')
    source = source.replace(f'# Cumulative reference stage {level - 1}:',
                            f'# Practice for stage {level}; starting from stage {level - 1}:', 1)
    destination.mkdir(parents=True)
    (destination / 'docker-compose.yml').write_text(source)
    shutil.copyfile(previous / 'security.sql', destination / 'security.sql')
    print(f'Starter created: {destination}\n'
          f'Implement layer {level}, then run:\n'
          f'python3 agent-security-workshop/layers.py check {level} --practice')


def check(level):
    """Rebuild/apply the learner configuration, then check actual running behavior."""
    try:
        up(level)
        test(level)
    except (SystemExit, OSError, subprocess.SubprocessError) as error:
        print(f'FAIL — stage {level}: deployment or behavior checks failed ({error}).', flush=True)
        return False
    print(f'PASS — stage {level}: all required behavior checks passed.', flush=True)
    return True


def verify_all():
    for level, name in enumerate(STAGES):
        print(f'\nChecking {name}', flush=True)
        try:
            up(level, build=level == 0)
            test(level)
        finally:
            # Keep data volumes for later demonstrations; stop only this stage.
            compose(level, 'down')
    print('All nine cumulative stages verified.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['list', 'prepare', 'check', 'up', 'test', 'down', 'audit', 'verify-all'])
    parser.add_argument('stage', type=level_for, nargs='?')
    parser.add_argument('--practice', action='store_true', help='Use the separate learner configuration and Docker project.')
    args = parser.parse_args()
    if args.practice:
        os.environ['AGENT_WORKSHOP_PRACTICE'] = '1'
    if args.command == 'verify-all' and args.practice:
        parser.error('verify-all checks completed reference folders; check practice stages individually')
    if args.command == 'list':
        print('\n'.join(STAGES))
    elif args.command == 'verify-all':
        verify_all()
    elif args.stage is None:
        parser.error('This command requires a stage number or folder name')
    elif args.command == 'prepare':
        prepare(args.stage)
    elif args.command == 'check':
        raise SystemExit(0 if check(args.stage) else 1)
    elif args.command == 'up':
        up(args.stage)
    elif args.command == 'test':
        test(args.stage)
    elif args.command == 'audit':
        setup(args.stage, 'audit')
    else:
        compose(args.stage, 'down')
