"""Share a local proxy token, never the OpenAI key, with the agent."""

import json
import os
from pathlib import Path
import secrets


broker = Path('/broker-config/access.json')
token = json.loads(broker.read_text())['model_token'] if broker.exists() else secrets.token_urlsafe(32)
access = {'model_token': token, 'model': os.environ['OPENAI_MODEL']}
for path in (broker, Path('/agent-config/access.json')):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(access))
    temporary.chmod(0o444)
    temporary.replace(path)
print('Local proxy credentials prepared; no OpenAI key was copied.')
