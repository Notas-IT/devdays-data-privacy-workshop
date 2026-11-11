"""Provision the synthetic gateway connection file without exposing it to the agent."""

import json
from pathlib import Path
import secrets


path = Path('/config/connection.json')
previous = json.loads(path.read_text()) if path.exists() else {}
password = previous.get('password') if previous.get('user') == 'gateway_reader' else None
temporary = path.with_suffix('.tmp')
temporary.write_text(json.dumps({
    'host': 'db', 'dbname': 'agent_lab', 'user': 'gateway_reader',
    'password': password or secrets.token_urlsafe(32), 'connect_timeout': 2,
}))
temporary.chmod(0o444)
temporary.replace(path)
print('Gateway configuration prepared.')

identity = Path('/identity-config/access.json')
previous_identity = json.loads(identity.read_text()) if identity.exists() else {}
temporary_identity = identity.with_suffix('.tmp')
temporary_identity.write_text(json.dumps({
    'gateway_token': previous_identity.get('gateway_token') or secrets.token_urlsafe(32),
}))
temporary_identity.chmod(0o444)
temporary_identity.replace(identity)
print('Agent gateway credential prepared.')
