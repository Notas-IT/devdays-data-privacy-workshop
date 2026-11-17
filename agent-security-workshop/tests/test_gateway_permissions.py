"""Exercise PostgreSQL permissions using the gateway's actual login."""

import json
from decimal import Decimal
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GatewayPermissionsTest(unittest.TestCase):
    def compose(self, *args, input=None):
        return subprocess.run(
            ['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml'), *args],
            input=input, capture_output=True, text=True, check=True, timeout=30,
        ).stdout

    def token(self):
        return self.compose('exec', '-T', 'agent', 'python', '-c',
            "import json; print(json.load(open('/run/identity/access.json'))['gateway_token'])").strip()

    def query(self, sql, before=None, params=None, read_only=True):
        return json.loads(self.compose('exec', '-T', 'gateway', 'python', '-c', '''
import json, sys, psycopg
from pathlib import Path
from psycopg.rows import dict_row
request = json.load(sys.stdin)
config = json.loads(Path('/run/gateway/connection.json').read_text())
with psycopg.connect(**config, autocommit=True, row_factory=dict_row) as connection:
    try:
        with connection.transaction():
            if request['read_only']:
                connection.execute('SET TRANSACTION READ ONLY')
            if request.get('before'):
                connection.execute(request['before'])
            cursor = connection.execute(request['sql'], request.get('params'))
            rows = cursor.fetchall() if cursor.description else []
    except psycopg.Error as error:
        result = {'ok': False, 'sqlstate': error.sqlstate}
    else:
        result = {'ok': True, 'rows': rows}
print(json.dumps(result, default=str))
''', input=json.dumps({'sql': sql, 'before': before, 'params': params, 'read_only': read_only})))

    def test_gateway_login_has_no_privileged_attributes(self):
        result = self.query('''SELECT current_user AS name, rolsuper, rolbypassrls,
            rolcreatedb, rolcreaterole, rolreplication, rolinherit
            FROM pg_roles WHERE rolname=current_user''')
        self.assertTrue(result['ok'])
        self.assertEqual(result['rows'], [{'name': 'gateway_reader', 'rolsuper': False,
            'rolbypassrls': False, 'rolcreatedb': False, 'rolcreaterole': False,
            'rolreplication': False, 'rolinherit': False}])

    def test_direct_salary_table_access_is_denied(self):
        for setting in (None, "SET LOCAL app.company_id='1'"):
            with self.subTest(company_setting=setting):
                result = self.query('SELECT salary_eur FROM lab_private.employee_salaries WHERE company_id=1', setting)
                self.assertFalse(result['ok'])
                self.assertEqual(result['sqlstate'], '42501')

    def test_summary_function_returns_only_the_fixed_aggregate(self):
        token = self.token()
        result = self.query('SELECT * FROM lab_api.salary_summary(%s, %s)',
            "SET LOCAL app.company_id='99999'", params=[token, 1])
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['rows']), 1)
        row = result['rows'][0]
        self.assertEqual(set(row), {'company_id', 'employee_count', 'average_salary_eur'})
        self.assertEqual(row['company_id'], 1)
        self.assertEqual(row['employee_count'], 3)
        self.assertEqual(Decimal(row['average_salary_eur']), Decimal('4000'))
        empty = self.query('SELECT count(*) AS count FROM lab_api.salary_summary(%s, %s)',
                           params=[token, 0])
        self.assertEqual(empty, {'ok': True, 'rows': [{'count': 0}]})

    def test_individual_salary_function_cannot_be_executed(self):
        result = self.query('SELECT * FROM lab_api.salary_rows(1)')
        self.assertFalse(result['ok'])
        self.assertEqual(result['sqlstate'], '42501')
        grant = self.query("SELECT has_function_privilege(current_user, 'lab_api.salary_rows(integer)', 'EXECUTE') AS allowed")
        self.assertEqual(grant, {'ok': True, 'rows': [{'allowed': False}]})

    def test_public_projects_remain_readable(self):
        result = self.query('SELECT project_id, title FROM lab_public.projects ORDER BY project_id')
        self.assertEqual(result, {'ok': True, 'rows': [
            {'project_id': 1, 'title': 'Conference schedule'},
            {'project_id': 2, 'title': 'Workshop materials'},
        ]})

    def test_privileged_role_changes_are_denied(self):
        for statement in ('SET ROLE lab_admin', 'SET ROLE layer_row_reader', 'SET ROLE lab_summary',
                          'SET ROLE lab_auth',
                          'SET SESSION AUTHORIZATION lab_admin'):
            with self.subTest(statement=statement):
                result = self.query(statement)
                self.assertFalse(result['ok'])
                self.assertEqual(result['sqlstate'], '42501')

    def test_summary_does_not_expose_individual_salary_columns(self):
        for column in ('employee_id', 'employee_name', 'salary_eur', 'security_canary'):
            with self.subTest(column=column):
                result = self.query(f'SELECT {column} FROM lab_api.salary_summary(%s, %s)',
                                    params=[self.token(), 1])
                self.assertFalse(result['ok'])
                self.assertEqual(result['sqlstate'], '42703')

    def test_function_owner_obeys_row_security(self):
        result = self.query('SELECT * FROM lab_api.salary_summary(%s, %s)',
                            'SET LOCAL row_security=off', params=[self.token(), 1])
        self.assertFalse(result['ok'])
        self.assertEqual(result['sqlstate'], '42501')
        policies = self.query("""SELECT policyname, roles FROM pg_policies
            WHERE schemaname='lab_private' AND tablename='employee_salaries'
            ORDER BY policyname""")
        self.assertEqual(policies, {'ok': True, 'rows': [
            {'policyname': 'layer_rows', 'roles': ['layer_row_reader']},
            {'policyname': 'layer_summary', 'roles': ['lab_summary']}]})

    def test_http_average_succeeds_and_individual_salaries_are_denied(self):
        result = json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
base = os.environ['GATEWAY_URL']
token = json.loads(Path('/run/identity/access.json').read_text())['gateway_token']
headers = {'Authorization': 'Bearer ' + token}
try:
    with urlopen(Request(base + '/companies/1/salaries', headers=headers), timeout=5) as response:
        individual_status = response.status
except HTTPError as error:
    individual_status = error.code
with urlopen(Request(base + '/companies/1/salary-summary', headers=headers), timeout=5) as response:
    summary = json.load(response)
print(json.dumps({'individual_status': individual_status, 'summary': summary}))
'''))
        self.assertEqual(result['individual_status'], 403)
        self.assertEqual(set(result['summary']), {'company_id', 'employee_count', 'average_salary_eur'})
        self.assertEqual(result['summary']['company_id'], 1)
        self.assertEqual(result['summary']['employee_count'], 3)
        self.assertEqual(Decimal(result['summary']['average_salary_eur']), Decimal('4000'))

    def test_open_summary_is_revoked(self):
        result = self.query('SELECT * FROM lab_api.open_salary_summary(1)')
        self.assertFalse(result['ok'])
        self.assertEqual(result['sqlstate'], '42501')
        grant = self.query("SELECT has_function_privilege(current_user, 'lab_api.open_salary_summary(integer)', 'EXECUTE') AS allowed")
        self.assertEqual(grant, {'ok': True, 'rows': [{'allowed': False}]})

    def test_audit_permissions_allow_insert_only(self):
        result = self.query("""SELECT
            has_table_privilege(current_user, 'lab_audit.events', 'INSERT') AS can_insert,
            has_table_privilege(current_user, 'lab_audit.events', 'SELECT') AS can_select,
            has_table_privilege(current_user, 'lab_audit.events', 'UPDATE') AS can_update,
            has_table_privilege(current_user, 'lab_audit.events', 'DELETE') AS can_delete,
            has_table_privilege(current_user, 'lab_audit.events', 'TRUNCATE') AS can_truncate""")
        self.assertEqual(result, {'ok': True, 'rows': [{'can_insert': True,
            'can_select': False, 'can_update': False, 'can_delete': False, 'can_truncate': False}]})
        for statement in (
            'SELECT * FROM lab_audit.events LIMIT 1',
            "UPDATE lab_audit.events SET outcome='denied' WHERE false",
            'DELETE FROM lab_audit.events WHERE false',
        ):
            with self.subTest(statement=statement):
                denied = self.query(statement, read_only=False)
                self.assertFalse(denied['ok'])
                self.assertEqual(denied['sqlstate'], '42501')

    def test_authenticate_returns_only_verified_identity(self):
        result = self.query('SELECT * FROM lab_api.authenticate(%s)', params=[self.token()])
        self.assertEqual(result, {'ok': True, 'rows': [{'actor': 'workshop-agent', 'company_id': 1}]})
        denied = self.query('SELECT token_hash FROM lab_control.credentials')
        self.assertFalse(denied['ok'])
        self.assertEqual(denied['sqlstate'], '42501')

    def test_invalid_expired_and_revoked_tokens_are_denied_by_database(self):
        for token in ('invalid-workshop-token', 'expired-workshop-token', 'revoked-workshop-token', None):
            with self.subTest(token=token):
                identity = self.query('SELECT * FROM lab_api.authenticate(%s)', params=[token])
                summary = self.query('SELECT * FROM lab_api.salary_summary(%s, %s)', params=[token, 1])
                self.assertEqual(identity, {'ok': True, 'rows': []})
                self.assertEqual(summary, {'ok': True, 'rows': []})

    def test_verified_company_cannot_be_overridden_by_session_setting(self):
        for company in (2, None):
            with self.subTest(company=company):
                result = self.query('SELECT * FROM lab_api.salary_summary(%s, %s)',
                    "SET LOCAL app.company_id='2'", params=[self.token(), company])
                self.assertEqual(result, {'ok': True, 'rows': []})

    def test_http_identity_headers_cannot_grant_company_permissions(self):
        result = json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
base = os.environ['GATEWAY_URL']
token = json.loads(Path('/run/identity/access.json').read_text())['gateway_token']
forged = {'X-Company-ID': '2', 'X-User': 'administrator', 'X-Role': 'admin'}
def call(path, credential):
    headers = dict(forged)
    if credential:
        headers['Authorization'] = 'Bearer ' + credential
    try:
        with urlopen(Request(base + path, headers=headers), timeout=5) as response:
            return {'status': response.status, 'body': json.load(response)}
    except HTTPError as error:
        return {'status': error.code}
outcomes = {
    'anonymous': call('/companies/2/salary-summary', None),
    'invalid': call('/companies/2/salary-summary', 'invalid-workshop-token'),
    'expired': call('/companies/1/salary-summary', 'expired-workshop-token'),
    'revoked': call('/companies/1/salary-summary', 'revoked-workshop-token'),
    'other_company': call('/companies/2/salary-summary', token),
    'identity': call('/me', token),
}
print(json.dumps(outcomes))
'''))
        for name in ('anonymous', 'invalid', 'expired', 'revoked'):
            self.assertEqual(result[name]['status'], 401)
        self.assertEqual(result['other_company']['status'], 403)
        self.assertEqual(result['identity'], {'status': 200,
            'body': {'actor': 'workshop-agent', 'company_id': 1}})


if __name__ == '__main__':
    unittest.main()
