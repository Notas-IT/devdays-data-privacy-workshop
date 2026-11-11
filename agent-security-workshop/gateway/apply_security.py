"""Apply gateway permissions to existing workshop data without resetting it."""

import json
import hashlib
import os
from pathlib import Path

import psycopg
from psycopg import sql


access = json.loads(Path('/run/gateway/connection.json').read_text())
identity = json.loads(Path('/run/identity/access.json').read_text())
with psycopg.connect(os.environ['ADMIN_DSN']) as connection:
    connection.execute(Path(__file__).with_name('security.sql').read_text())
    connection.execute(sql.SQL('ALTER ROLE gateway_reader PASSWORD {}').format(
        sql.Literal(access['password'])))
    for token, actor, active, lifetime in (
        (identity['gateway_token'], 'workshop-agent', True, '1 day'),
        ('expired-workshop-token', 'expired-agent', True, '-1 day'),
        ('revoked-workshop-token', 'revoked-agent', False, '1 day'),
    ):
        connection.execute('''INSERT INTO lab_control.credentials
            (token_hash, actor, company_id, active, expires_at)
            VALUES (%s, %s, 1, %s, clock_timestamp() + %s::interval)
            ON CONFLICT(token_hash) DO UPDATE SET actor=EXCLUDED.actor,
                company_id=EXCLUDED.company_id, active=EXCLUDED.active,
                expires_at=EXCLUDED.expires_at''',
            (hashlib.sha256(token.encode()).hexdigest(), actor, active, lifetime))
print('Gateway function permissions applied; existing data preserved.')
