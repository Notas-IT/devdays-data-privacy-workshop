"""Credential-injecting Responses proxy, not a general outbound HTTP proxy."""

import hmac
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import threading
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request

UPSTREAM = 'https://api.openai.com/v1/responses'
MAX_REQUEST_BYTES = 2_000_000
MAX_OUTPUT_TOKENS = 4096


def validate_limit(limit):
    if type(limit) is not int or not 0 < limit < 2**63:
        raise ValueError('Request limit must be a positive integer')


class MemoryBudget:
    persistent = False

    def __init__(self, limit):
        validate_limit(limit)
        self.limit, self.used, self.lock = limit, 0, threading.Lock()

    def take(self):
        with self.lock:
            if self.used >= self.limit:
                return False
            self.used += 1
            return True

    def snapshot(self):
        with self.lock:
            return self.used


class SQLiteBudget:
    """Atomically reserve usage before forwarding, including across restarts."""
    persistent = True

    def __init__(self, path, limit):
        validate_limit(limit)
        self.path, self.limit = str(path), limit
        with closing(self.connect()) as connection, connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS budget (
                id INTEGER PRIMARY KEY CHECK (id=1), used INTEGER NOT NULL CHECK (used>=0))''')
            connection.execute('INSERT OR IGNORE INTO budget VALUES (1, 0)')

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute('PRAGMA synchronous=FULL')
        return connection

    def take(self):
        with closing(self.connect()) as connection, connection:
            cursor = connection.execute('UPDATE budget SET used=used+1 WHERE id=1 AND used<?',
                                        (self.limit,))
            return cursor.rowcount == 1

    def snapshot(self):
        with closing(self.connect()) as connection:
            row = connection.execute('SELECT used FROM budget WHERE id=1').fetchone()
            if row is None:
                raise sqlite3.DatabaseError('Missing budget record')
            return row[0]


def reject_nonfinite(value):
    raise ValueError('Non-finite JSON numbers are unsupported')


def local_tools_only(tools):
    if not isinstance(tools, list):
        return False
    for tool in tools:
        if not isinstance(tool, dict):
            return False
        if tool.get('type') in ('function', 'custom'):
            continue
        if tool.get('type') == 'namespace' and local_tools_only(tool.get('tools')):
            continue
        return False
    return True


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def handler_factory(token, api_key, model, *, limit=60, opener=None, budget=None):
    validate_limit(limit)
    if not isinstance(token, str) or not token or not isinstance(model, str) or not model.strip():
        raise ValueError('A local proxy token and allowed model are required')
    if not isinstance(api_key, str) or (api_key and token == api_key):
        raise ValueError('The local token must be separate from the provider credential')
    budget = budget if budget is not None else MemoryBudget(limit)
    if budget.limit != limit:
        raise ValueError('Budget and configured request limits must match')
    open_upstream = opener or build_opener(ProxyHandler({}), NoRedirect()).open

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, value):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

        def authenticated(self):
            values = self.headers.get_all('Authorization', [])
            return len(values) == 1 and hmac.compare_digest(
                values[0].encode('utf-8'), ('Bearer ' + token).encode('utf-8'))

        def do_GET(self):
            if self.path == '/health':
                configured = bool(api_key and model)
                self.respond(200 if configured else 503,
                    {'status': 'ok' if configured else 'unconfigured', 'configured': configured})
            elif self.path == '/policy':
                if not self.authenticated():
                    self.respond(401, {'error': 'Invalid broker credential'})
                    return
                try:
                    used = budget.snapshot()
                except (sqlite3.Error, OSError):
                    self.respond(503, {'error': 'Usage accounting unavailable'})
                    return
                self.respond(200, {'upstream': UPSTREAM, 'model': model,
                    'request_limit': limit, 'requests_used': used,
                    'requests_remaining': max(0, limit - used),
                    'max_request_bytes': MAX_REQUEST_BYTES, 'max_output_tokens': MAX_OUTPUT_TOKENS,
                    'persistent_budget': budget.persistent})
            else:
                self.respond(404, {'error': 'No such broker endpoint'})

        def do_POST(self):
            if self.path != '/v1/responses':
                self.respond(404, {'error': 'Only the Responses endpoint is available'})
                return
            if not self.authenticated():
                self.respond(401, {'error': 'Invalid broker credential'})
                return
            encodings = self.headers.get_all('Content-Encoding', [])
            if encodings and [item.lower() for item in encodings] != ['identity']:
                self.respond(415, {'error': 'Compressed model requests are not supported'})
                return
            try:
                lengths = self.headers.get_all('Content-Length', [])
                if self.headers.get_all('Transfer-Encoding', []) or len(lengths) != 1:
                    raise ValueError()
                if not lengths[0].isascii() or not lengths[0].isdigit():
                    raise ValueError()
                length = int(lengths[0])
                if not 0 < length <= MAX_REQUEST_BYTES:
                    self.respond(413, {'error': 'Model request length must be between 1 and 2000000 bytes'})
                    return
                self.connection.settimeout(10)
                body = json.loads(self.rfile.read(length), parse_constant=reject_nonfinite)
                if not isinstance(body, dict) or body.get('model') != model:
                    self.respond(400, {'error': 'Model name is not allowed'})
                    return
                # The CLI may use local function/custom tools, not upstream
                # web/file/computer tools with separate data/egress capabilities.
                if not local_tools_only(body.get('tools', [])):
                    self.respond(400, {'error': 'Unsupported upstream tool type',
                        'detail': 'Only local function/custom tools and their namespaces are allowed'})
                    return
                body['store'] = False
                maximum = body.get('max_output_tokens', MAX_OUTPUT_TOKENS)
                if type(maximum) is not int or maximum <= 0:
                    raise ValueError()
                body['max_output_tokens'] = min(maximum, MAX_OUTPUT_TOKENS)
                if body.get('background', False) is not False or type(body.get('stream', False)) is not bool:
                    raise ValueError()
                payload = json.dumps(body, allow_nan=False).encode()
            except TimeoutError:
                self.respond(408, {'error': 'Timed out reading model request'})
                return
            except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
                self.respond(400, {'error': 'Invalid or disallowed model request'})
                return
            if not api_key or not model:
                self.respond(503, {'error': 'Presenter has not configured the model provider'})
                return
            try:
                allowed = budget.take()
            except (sqlite3.Error, OSError):
                self.respond(503, {'error': 'Usage accounting unavailable'})
                return
            if not allowed:
                self.respond(429, {'error': 'Workshop model request budget exhausted'})
                return
            call = Request(UPSTREAM, data=payload, headers={
                'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json',
                'Accept': 'text/event-stream' if body.get('stream') else 'application/json'})
            try:
                response = open_upstream(call, timeout=90)
                with response:
                    self.send_response(response.status)
                    self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    while chunk := response.read1(65536):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    self.close_connection = True
            except HTTPError as error:
                # Upstream error bodies/headers may include provider metadata.
                self.respond(502, {'error': 'Model provider rejected the request', 'provider_status': error.code})
            except (URLError, TimeoutError):
                self.respond(502, {'error': 'Model provider unavailable'})
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_CONNECT(self):
            self.respond(405, {'error': 'General outbound proxying is disabled'})

    return Handler


if __name__ == '__main__':
    token = json.loads(Path('/run/broker/access.json').read_text())['model_token']
    limit = int(os.environ.get('MODEL_REQUEST_LIMIT', '60'))
    budget = SQLiteBudget('/state/model-usage.sqlite3', limit)
    handler = handler_factory(token, os.environ.get('OPENAI_API_KEY', ''),
        os.environ.get('OPENAI_MODEL', ''), limit=limit, budget=budget)
    ThreadingHTTPServer(('0.0.0.0', 8081), handler).serve_forever()
