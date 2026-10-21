"""A deliberately small authenticated API; there is no SQL/proxy/file endpoint."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid

import psycopg
from psycopg.rows import dict_row

CONFIG = json.loads(Path('/run/gateway/connection.json').read_text())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Default HTTP logs contain attacker-controlled paths/queries.

    def respond(self, status, body, request_id):
        data = json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Request-ID', request_id)
        if status == 401:
            self.send_header('WWW-Authenticate', 'Bearer')
        self.end_headers()
        self.wfile.write(data)

    def handle_request(self):
        request_id = str(uuid.uuid4())
        url = urlsplit(self.path)
        if self.command == 'GET' and url.path == '/health':
            try:
                with psycopg.connect(**CONFIG) as connection:
                    connection.execute('SELECT 1')
                self.respond(200, {'status': 'ok'}, request_id)
            except psycopg.Error:
                self.respond(503, {'error': 'Database unavailable'}, request_id)
            return

        authorization = self.headers.get('Authorization', '')
        token = authorization[7:] if authorization.startswith('Bearer ') else ''
        status, body, actor, company_id, action = 401, {'error': 'Authentication required'}, None, None, 'authenticate'
        try:
            with psycopg.connect(**CONFIG, row_factory=dict_row) as connection:
                caller = None
                if token and len(token) <= 512:
                    caller = connection.execute('SELECT * FROM lab_api.authenticate(%s)', (token,)).fetchone()
                if caller:
                    actor = caller['actor']
                    if self.command != 'GET':
                        status, body, action = 405, {'error': 'Method not allowed'}, 'unsupported_method'
                    elif url.query:
                        status, body, action = 400, {'error': 'Query parameters are not supported'}, 'unsupported_query'
                    elif url.path == '/me':
                        status, body, action = 200, caller, 'identity'
                    elif url.path == '/projects':
                        body = {'items': connection.execute('SELECT * FROM lab_public.projects ORDER BY project_id').fetchall()}
                        status, action = 200, 'projects'
                    elif match := re.fullmatch(r'/companies/([0-9]{1,9})/salary-summary', url.path):
                        company_id = int(match[1])
                        action = 'salary_summary'
                        row = connection.execute('SELECT * FROM lab_api.salary_summary(%s,%s)', (token, company_id)).fetchone()
                        status, body = (200, row) if row else (403, {'error': 'Permission denied'})
                    elif re.fullmatch(r'/employees/[^/]+/salary', url.path):
                        status, body, action = 403, {'error': 'Individual salaries are not available'}, 'individual_salary'
                    elif url.path.startswith('/admin'):
                        status, body, action = 403, {'error': 'Permission denied'}, 'admin'
                    else:
                        status, body, action = 404, {'error': 'Not found'}, 'unknown_route'
                connection.execute('''INSERT INTO lab_audit.events
                    (request_id, actor, action, company_id, status, outcome)
                    VALUES (%s,%s,%s,%s,%s,%s)''',
                    (request_id, actor, action, company_id, status, 'allowed' if status < 400 else 'denied'))
            # Commit the audit before sending data. An audit failure fails closed.
        except psycopg.Error:
            status, body = 503, {'error': 'Database or audit unavailable'}
        self.respond(status, body, request_id)

    do_GET = handle_request
    do_POST = handle_request
    do_PUT = handle_request
    do_DELETE = handle_request


if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', 8000), Handler)
    server.serve_forever()
