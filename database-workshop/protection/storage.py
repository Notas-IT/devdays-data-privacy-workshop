"""Credentials stay in the API runtime volume; audit rows exclude sensitive values."""

from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

RUNTIME = Path(os.environ.get("API_RUNTIME", "/runtime"))


def settings():
    return json.loads((RUNTIME / "connection.json").read_text())


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def private_hash(value):
    return hmac.new(bytes.fromhex(settings()["audit_pepper"]), value.encode(), hashlib.sha256).hexdigest()


@contextmanager
def database(actor_id=None):
    config = settings()
    with psycopg.connect(**config["database"], row_factory=dict_row) as connection:
        if actor_id is not None:
            connection.execute("SELECT set_config('app.account_id', %s, true)", (str(actor_id),))
        yield connection


def record_audit(connection, request, status, *, action=None, details=None):
    actor = getattr(request.state, "actor", None)
    connection.execute("""INSERT INTO security_audit.events
        (request_id,actor_id,action,resource_kind,resource_id,outcome,http_status,policy_revision,details)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (request.state.request_id, actor["account_id"] if actor else None,
         action or getattr(request.state, "action", "request"),
         getattr(request.state, "resource_kind", None), getattr(request.state, "resource_id", None),
         "allowed" if status < 400 else "denied" if status < 500 else "failed", status,
         actor["policy_revision"] if actor else None, Jsonb(details or {})))
