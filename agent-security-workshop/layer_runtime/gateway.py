"""One gateway implementation, with independently deployed cumulative stages."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid

import psycopg
from psycopg.rows import dict_row

LEVEL = int(os.environ['STAGE_LEVEL'])
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
        self.wfile.write(payload)

    def handle_request(self):
        request_id = str(uuid.uuid4())
        url = urlsplit(self.path)
        if self.command == 'GET' and url.path == '/health':
            self.reply(200, {'status': 'ok', 'stage': LEVEL}, request_id)
            return
        authorization = self.headers.get('Authorization', '')
        token = authorization[7:] if authorization.startswith('Bearer ') else ''
        status, body, action, requested_company = 401, {'error': 'Authentication required'}, 'authenticate', None
        actor = None
        try:
            with psycopg.connect(**CONFIG, row_factory=dict_row) as connection:
                caller = {'actor': 'shared-gateway', 'company_id': None}
                if LEVEL >= 7:
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
                    elif url.path == '/projects':
                        status, action = 200, 'projects'
                        body = {'items': connection.execute('SELECT * FROM lab_public.projects ORDER BY project_id').fetchall()}
                    elif match := re.fullmatch(r'/companies/([0-9]{1,9})/(salaries|salary-summary)', url.path):
                        requested_company = int(match[1])
                        if match[2] == 'salaries':
                            action = 'individual_salaries'
                            if LEVEL >= 6:
                                status, body = 403, {'error': 'Individual salaries are not available'}
                            elif LEVEL == 5:
                                rows = connection.execute('SELECT * FROM lab_api.salary_rows(%s)', (requested_company,)).fetchall()
                                status, body = 200, {'items': rows}
                            else:
                                rows = connection.execute('SELECT * FROM lab_private.employee_salaries WHERE company_id=%s',
                                    (requested_company,)).fetchall()
                                status, body = 200, {'items': rows}
                        else:
                            action = 'salary_summary'
                            if LEVEL >= 7:
                                row = connection.execute('SELECT * FROM lab_api.salary_summary(%s,%s)',
                                    (token, requested_company)).fetchone()
                            elif LEVEL == 6:
                                row = connection.execute('SELECT * FROM lab_api.open_salary_summary(%s)',
                                    (requested_company,)).fetchone()
                            elif LEVEL == 5:
                                row = connection.execute('''SELECT company_id,count(*) AS employee_count,
                                    avg(salary_eur) AS average_salary_eur FROM lab_api.salary_rows(%s)
                                    GROUP BY company_id''', (requested_company,)).fetchone()
                            else:
                                row = connection.execute('''SELECT company_id,count(*) AS employee_count,
                                    avg(salary_eur) AS average_salary_eur FROM lab_private.employee_salaries
                                    WHERE company_id=%s GROUP BY company_id''', (requested_company,)).fetchone()
                            status, body = (200, row) if row else (403, {'error': 'Not permitted or cohort too small'})
                    else:
                        status, body, action = 404, {'error': 'Not found'}, 'unknown_route'
                if LEVEL >= 8:
                    connection.execute('''INSERT INTO lab_audit.events
                        (request_id,actor,action,company_id,status,outcome) VALUES (%s,%s,%s,%s,%s,%s)''',
                        (request_id, actor, action, requested_company, status, 'allowed' if status < 400 else 'denied'))
            # Stage 8 commits the audit before any data leaves the API.
        except psycopg.Error:
            status, body = 503, {'error': 'Database or audit unavailable'}
        self.reply(status, body, request_id)

    do_GET = handle_request
    do_POST = handle_request
    do_PUT = handle_request
    do_DELETE = handle_request


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
