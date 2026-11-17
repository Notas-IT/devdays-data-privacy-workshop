"""Authenticated aggregate gateway, adapted from the instructor's reference.

Only database-verified bearer tokens determine identity and company access.
"""

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
        pass

    def reply(self, status, body, request_id):
        payload = json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Request-ID', request_id)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(payload)

    def handle_request(self):
        request_id = str(uuid.uuid4())
        url = urlsplit(self.path)
        if self.command == 'GET' and url.path == '/health' and not url.query:
            try:
                with psycopg.connect(**CONFIG) as connection:
                    connection.execute('SELECT 1')
                self.reply(200, {'status': 'ok'}, request_id)
            except psycopg.Error:
                self.reply(503, {'error': 'Database unavailable'}, request_id)
            return

        actor, company_id, action = None, None, 'authenticate'
        status, body = 401, {'error': 'Authentication required'}
        try:
            with psycopg.connect(**CONFIG, row_factory=dict_row) as connection:
                authorization = self.headers.get_all('Authorization', [])
                value = authorization[0] if len(authorization) == 1 else ''
                token = value[7:] if value.startswith('Bearer ') else ''
                caller = connection.execute('SELECT * FROM lab_api.authenticate(%s)',
                    (token if len(token) <= 512 else '',)).fetchone()
                if caller:
                    actor = caller['actor']
                    if self.command != 'GET':
                        status, body, action = 405, {'error': 'Method not allowed'}, 'unsupported_method'
                    elif url.query:
                        status, body, action = 400, {'error': 'Query parameters are not supported'}, 'unsupported_query'
                    elif url.path == '/me':
                        status, body, action = 200, caller, 'identity'
                        company_id = caller['company_id']
                    elif url.path == '/projects':
                        rows = connection.execute('SELECT * FROM lab_public.projects ORDER BY project_id').fetchall()
                        status, body, action = 200, {'items': rows}, 'projects'
                    elif match := re.fullmatch(r'/companies/([0-9]{1,9})/(salaries|salary-summary)', url.path):
                        company_id = int(match[1])
                        if match[2] == 'salaries':
                            status, body, action = 403, {'error': 'Individual salaries are not available'}, 'individual_salaries'
                        else:
                            action = 'salary_summary'
                            row = connection.execute('SELECT * FROM lab_api.salary_summary(%s, %s)',
                                                     (token, company_id)).fetchone()
                            status, body = (200, row) if row else (403, {'error': 'Permission denied'})
                    else:
                        status, body, action = 404, {'error': 'Not found'}, 'unknown_route'
                connection.execute('''INSERT INTO lab_audit.events
                    (request_id, actor, action, company_id, status, outcome)
                    VALUES (%s, %s, %s, %s, %s, %s)''',
                    (request_id, actor, action, company_id, status,
                     'allowed' if status < 400 else 'denied'))
            # The context manager commits before any business response is sent.
        except psycopg.Error:
            status, body = 503, {'error': 'Database or audit unavailable'}
            print(json.dumps({'event': 'database_or_audit_failure',
                              'request_id': request_id, 'status': status}), flush=True)
        self.reply(status, body, request_id)

    do_GET = handle_request
    do_POST = handle_request
    do_PUT = handle_request
    do_DELETE = handle_request
    do_PATCH = handle_request
    do_HEAD = handle_request
    do_OPTIONS = handle_request


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
