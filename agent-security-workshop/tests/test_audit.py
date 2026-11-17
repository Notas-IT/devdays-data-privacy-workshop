"""Check real audit commits, denied requests and recovery from audit failure."""

import json
from pathlib import Path
import subprocess
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]


class AuditTest(unittest.TestCase):
    def compose(self, *args, input=None):
        return subprocess.run(
            ['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml'), *args],
            input=input, capture_output=True, text=True, check=True, timeout=30,
        ).stdout

    def admin(self, sql):
        return self.compose('exec', '-T', 'db', 'psql', '-X', '-q', '-A', '-t',
                            '-v', 'ON_ERROR_STOP=1', '-U', 'lab_admin', '-d', 'agent_lab', '-c', sql).strip()

    def call(self, path, authenticated=True, method='GET'):
        return json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, os, sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
arguments = json.load(sys.stdin)
headers = {'X-User': 'forged-administrator'}
if arguments['authenticated']:
    token = json.loads(Path('/run/identity/access.json').read_text())['gateway_token']
    headers['Authorization'] = 'Bearer ' + token
request = Request(os.environ['GATEWAY_URL'] + arguments['path'], headers=headers,
                  method=arguments['method'])
try:
    response = urlopen(request, timeout=10)
except HTTPError as error:
    response = error
with response:
    print(json.dumps({'status': response.status, 'body': json.load(response),
                      'request_id': response.headers.get('X-Request-ID')}))
''', input=json.dumps({'path': path, 'authenticated': authenticated, 'method': method})))

    def audit_row(self, request_id):
        request_id = str(uuid.UUID(request_id))
        row = self.admin(f"SELECT row_to_json(e) FROM lab_audit.events AS e WHERE request_id='{request_id}'::uuid")
        self.assertTrue(row, 'The response must have a committed audit event')
        return json.loads(row)

    def test_allowed_denied_and_unauthenticated_requests_have_committed_events(self):
        cases = [
            ('/companies/1/salary-summary', True, 'GET', 200, 'salary_summary', 1),
            ('/companies/2/salary-summary', True, 'GET', 403, 'salary_summary', 2),
            ('/companies/1/salaries', True, 'GET', 403, 'individual_salaries', 1),
            ('/projects', False, 'GET', 401, 'authenticate', None),
            ('/projects', True, 'GET', 200, 'projects', None),
            ('/projects', True, 'POST', 405, 'unsupported_method', None),
            ('/projects?marker=DO_NOT_LOG_THIS', True, 'GET', 400, 'unsupported_query', None),
        ]
        for path, authenticated, method, status, action, company_id in cases:
            with self.subTest(path=path, method=method, authenticated=authenticated):
                response = self.call(path, authenticated, method)
                self.assertEqual(response['status'], status)
                row = self.audit_row(response['request_id'])
                self.assertEqual(row['status'], status)
                self.assertEqual(row['action'], action)
                self.assertEqual(row['company_id'], company_id)
                self.assertEqual(row['actor'], 'workshop-agent' if authenticated else None)
                self.assertEqual(row['outcome'], 'allowed' if status < 400 else 'denied')
                self.assertEqual(set(row), {'event_id', 'occurred_at', 'request_id', 'actor',
                                           'action', 'company_id', 'status', 'outcome'})
                self.assertNotIn('DO_NOT_LOG_THIS', json.dumps(row))
                self.assertNotIn('forged-administrator', json.dumps(row))

    def test_insert_failure_withholds_data_and_recovers_after_restoring_grant(self):
        had_insert = self.admin("SELECT has_table_privilege('gateway_reader', 'lab_audit.events', 'INSERT')") == 't'
        try:
            self.admin('REVOKE INSERT ON lab_audit.events FROM gateway_reader')
            response = self.call('/companies/1/salary-summary')
            self.assertEqual(response['status'], 503)
            self.assertEqual(response['body'], {'error': 'Database or audit unavailable'})
            request_id = str(uuid.UUID(response['request_id']))
            self.assertEqual(self.admin(f"SELECT count(*) FROM lab_audit.events WHERE request_id='{request_id}'::uuid"), '0')
        finally:
            self.admin(('GRANT INSERT ON lab_audit.events TO' if had_insert else
                        'REVOKE INSERT ON lab_audit.events FROM') + ' gateway_reader')
        self.assertTrue(had_insert, 'Deploy INSERT permissions before running the suite')
        recovered = self.call('/companies/1/salary-summary')
        self.assertEqual(recovered['status'], 200)
        self.audit_row(recovered['request_id'])

    def test_handler_commit_order_and_commit_failure(self):
        self.compose('exec', '-T', 'gateway', 'python', '-m', 'unittest', 'test_audit_commit', '-v')


if __name__ == '__main__':
    unittest.main()
