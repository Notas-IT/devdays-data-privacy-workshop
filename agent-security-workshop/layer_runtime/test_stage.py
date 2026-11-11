"""Check real running boundaries, including deliberate gaps before later stages."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from layers import ROOT, STAGES, compose, setup

LEVEL = int(os.environ['AGENT_WORKSHOP_STAGE'])


def inspect(service):
    result = compose(LEVEL, 'ps', '-q', service, capture=True)
    if not result.stdout.strip():
        raise RuntimeError('Start this stage with layers.py up before testing')
    return json.loads(subprocess.check_output(['docker', 'inspect', result.stdout.strip()], text=True))[0]


class StageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = inspect('agent')
        cls.database = inspect('db')
        cls.outputs = []

    @classmethod
    def tearDownClass(cls):
        result = setup(LEVEL, 'observe', capture=True, data='\n'.join(cls.outputs))
        if result.returncode:
            raise AssertionError('Trusted output observation failed')
        observation = json.loads(result.stdout)
        if observation['privileged_secret_present']:
            raise AssertionError('A privileged presenter credential was exposed')
        if observation['canary_present'] != (LEVEL < 5):
            raise AssertionError('Actual raw-data exposure did not match this stage boundary')

    def agent_exec(self, *arguments):
        result = compose(LEVEL, 'exec', '-T', 'agent', *arguments, capture=True, timeout=15)
        self.outputs.extend([result.stdout, result.stderr])
        return result

    def api(self, path, *arguments):
        if LEVEL < 4:
            self.skipTest('The gateway is introduced at stage 4')
        result = self.agent_exec('python', '/opt/agent/client.py', 'api', path, *arguments)
        self.assertEqual(result.returncode, 0, 'The real gateway request must complete')
        return json.loads(result.stdout)

    def test_process_permissions(self):
        result = self.agent_exec('python', '-c', '''import json,os
s=dict(line.split(":",1) for line in open("/proc/self/status") if ":" in line)
print(json.dumps({"uid":os.getuid(),"caps":int(s["CapEff"].strip(),16),"nnp":s["NoNewPrivs"].strip()}))''')
        self.assertEqual(result.returncode, 0)
        value = json.loads(result.stdout)
        if LEVEL >= 1:
            self.assertEqual(value, {'uid': 10001, 'caps': 0, 'nnp': '1'})
        else:
            self.assertEqual(value['uid'], 0)
            self.assertNotEqual(value['caps'], 0)
            self.assertEqual(value['nnp'], '0')
        self.assertFalse(self.agent['HostConfig']['Privileged'])

    def test_filesystem_boundary(self):
        result = self.agent_exec('python', '-c', 'open("/workspace/file-test", "w").write("workshop")')
        self.assertEqual(result.returncode == 0, LEVEL < 2)
        self.assertEqual(self.agent['HostConfig']['ReadonlyRootfs'], LEVEL >= 2)
        result = self.agent_exec('python', '-c', 'open("/tmp/file-test", "w").write("workshop")')
        self.assertEqual(result.returncode, 0)

    def test_host_boundary_uses_a_harmless_fixture(self):
        mounts = self.agent['Mounts']
        binds = [mount for mount in mounts if mount['Type'] == 'bind']
        self.assertEqual(len(binds), 1 if LEVEL < 3 else 0)
        result = self.agent_exec('python', '-c', '''from pathlib import Path
import hashlib
p=Path('/host-workshop/host-fixture.txt')
print(hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else 'not-mounted')''')
        self.assertEqual(result.returncode, 0)
        if LEVEL < 3:
            self.assertEqual(result.stdout.strip(), hashlib.sha256((ROOT / 'host-fixture.txt').read_bytes()).hexdigest())
            self.assertFalse(binds[0]['RW'])
            self.assertEqual(Path(binds[0]['Source']).resolve(), (ROOT / 'host-fixture.txt').resolve())
        else:
            self.assertEqual(result.stdout.strip(), 'not-mounted')
        self.assertNotEqual(self.agent['HostConfig']['PidMode'], 'host')
        self.assertFalse(self.agent['HostConfig']['Devices'])
        self.assertFalse(self.database['HostConfig']['PortBindings'])

    def test_network_by_service_name_and_actual_database_ip(self):
        agent_networks = set(self.agent['NetworkSettings']['Networks'])
        db_networks = self.database['NetworkSettings']['Networks']
        common = agent_networks & set(db_networks)
        self.assertEqual(bool(common), LEVEL < 4)
        selected_network = sorted(common or set(db_networks))[0]
        for target in ['db', db_networks[selected_network]['IPAddress']]:
            with self.subTest(target=target):
                result = self.agent_exec('python', '-c',
                    'import socket,sys; socket.create_connection((sys.argv[1],5432),timeout=2).close()', target)
                self.assertEqual(result.returncode == 0, LEVEL < 4)

    def test_real_direct_sql_access(self):
        result = self.agent_exec('python', '/opt/agent/client.py', 'sql',
            'SELECT * FROM lab_private.employee_salaries ORDER BY employee_id')
        if LEVEL < 4:
            self.assertEqual(result.returncode, 0)
            self.assertEqual(len(json.loads(result.stdout)), 7)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Direct database credentials are not available', result.stderr)

    def test_database_grants_with_actual_queries(self):
        result = setup(LEVEL, 'queries', capture=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {
            'raw_select': LEVEL < 5, 'row_function': LEVEL == 5, 'open_summary': LEVEL == 6,
            'identity_summary': LEVEL >= 7, 'role_change': False, 'audit_delete': False})

    def test_gateway_returns_an_allowed_average(self):
        response = self.api('/companies/1/salary-summary')
        self.assertEqual(response['status'], 200)
        self.assertEqual(response['body']['company_id'], 1)
        self.assertEqual(float(response['body']['average_salary_eur']), 4000)

    def test_unsupported_methods_are_rejected(self):
        self.assertEqual(self.api('/projects', '--method', 'POST')['status'], 405)

    def test_individual_rows_remain_exposed_until_aggregate_layer(self):
        response = self.api('/companies/2/salaries')
        self.assertEqual(response['status'], 200 if LEVEL < 6 else 403)
        if LEVEL < 6:
            self.assertEqual(len(response['body']['items']), 3)
            self.assertEqual('security_canary' in response['body']['items'][0], LEVEL < 5)

    def test_small_cohort_is_suppressed_from_aggregate_layer(self):
        response = self.api('/companies/3/salary-summary')
        self.assertEqual(response['status'], 200 if LEVEL < 6 else 403)
        if LEVEL < 6:
            self.assertEqual(float(response['body']['average_salary_eur']), 8000)

    def test_identity_and_other_company_boundary(self):
        response = self.api('/companies/2/salary-summary')
        self.assertEqual(response['status'], 200 if LEVEL < 7 else 403)
        anonymous = self.api('/companies/1/salary-summary', '--anonymous')
        self.assertEqual(anonymous['status'], 200 if LEVEL < 7 else 401)
        spoofed = self.api('/companies/2/salary-summary', '--header', 'X-User=admin', '--header', 'X-Account-ID=admin')
        self.assertEqual(spoofed['status'], 200 if LEVEL < 7 else 403)
        if LEVEL >= 7:
            self.assertEqual(self.api('/me')['body'], {'actor': 'workshop-agent', 'company_id': 1})

    def test_audit_is_added_only_in_final_stage(self):
        if LEVEL >= 4:
            self.api('/projects')
        if LEVEL >= 8:
            self.api('/companies/2/salary-summary')
        result = setup(LEVEL, 'audit', capture=True)
        self.assertEqual(result.returncode, 0)
        rows = json.loads(result.stdout)
        self.assertEqual(bool(rows), LEVEL >= 8)
        if LEVEL >= 8:
            self.assertTrue(any(row['outcome'] == 'allowed' for row in rows))
            self.assertTrue(any(row['outcome'] == 'denied' for row in rows))
            self.assertFalse(any(row['outcome'] == 'allowed' and row['company_id'] == 2 for row in rows))

    def test_audit_failure_withholds_data(self):
        if LEVEL < 8:
            self.skipTest('Audit is introduced at stage 8')
        result = setup(LEVEL, 'audit-failure', capture=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {'status': 503, 'contains_average': False})
