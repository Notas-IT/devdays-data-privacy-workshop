"""Run a Codex task inside the isolated workshop workspace."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prompt')
    parser.add_argument('--model')
    args = parser.parse_args()
    access = json.loads(Path('/run/agent/access.json').read_text())
    model = access['model']
    if args.model and args.model != model:
        parser.error('Set OPENAI_MODEL on the host and recreate the services to change the allowed model')
    command = ['codex', 'exec', '--skip-git-repo-check',
               '--sandbox', 'danger-full-access', '--model', model]
    command.append(args.prompt)
    environment = dict(os.environ)
    environment['WORKSHOP_MODEL_TOKEN'] = access['model_token']
    proxy = os.environ['MODEL_PROXY_URL'].rstrip('/') + '/v1'
    with tempfile.TemporaryDirectory(prefix='codex-', dir='/home/agent') as home:
        environment['CODEX_HOME'] = home
        Path(home, 'config.toml').write_text(f'''model = {json.dumps(model)}
model_provider = "workshop"
web_search = "disabled"
[model_providers.workshop]
name = "Workshop model proxy"
base_url = {json.dumps(proxy)}
env_key = "WORKSHOP_MODEL_TOKEN"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
''')
        return subprocess.run(command, stdin=subprocess.DEVNULL, env=environment).returncode


if __name__ == "__main__":
    raise SystemExit(main())
