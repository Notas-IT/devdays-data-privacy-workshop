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

    def reply(self, status, body):
        payload = json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Request-ID', str(uuid.uuid4()))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.query:
            self.reply(400, {'error': 'Query parameters are not supported'})
            return
        try:
            with psycopg.connect(**CONFIG, row_factory=dict_row) as connection:
                connection.execute('SET TRANSACTION READ ONLY')
                if url.path == '/health':
                    connection.execute('SELECT 1')
                    self.reply(200, {'status': 'ok'})
                    return
                authorization = self.headers.get_all('Authorization', [])
                value = authorization[0] if len(authorization) == 1 else ''
                token = value[7:] if value.startswith('Bearer ') else ''
                caller = connection.execute('SELECT * FROM lab_api.authenticate(%s)',
                    (token if len(token) <= 512 else '',)).fetchone()
                if not caller:
                    self.reply(401, {'error': 'Authentication required'})
                    return
                if url.path == '/me':
                    status, body = 200, caller
                elif url.path == '/projects':
                    rows = connection.execute('SELECT * FROM lab_public.projects ORDER BY project_id').fetchall()
                    status, body = 200, {'items': rows}
                elif match := re.fullmatch(r'/companies/([0-9]{1,9})/(salaries|salary-summary)', url.path):
                    company_id = int(match[1])
                    if match[2] == 'salaries':
                        status, body = 403, {'error': 'Individual salaries are not available'}
                    else:
                        row = connection.execute('SELECT * FROM lab_api.salary_summary(%s, %s)',
                                                 (token, company_id)).fetchone()
                        status, body = (200, row) if row else (403, {'error': 'Permission denied'})
                else:
                    status, body = 404, {'error': 'Not found'}
        except psycopg.Error:
            status, body = 503, {'error': 'Database unavailable'}
        self.reply(status, body)

    def unsupported_method(self):
        self.reply(405, {'error': 'Method not allowed'})

    do_POST = unsupported_method
    do_PUT = unsupported_method
    do_DELETE = unsupported_method


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
