"""Host-run containment tests; no Docker socket is ever exposed to the agent."""

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

from lab import ROOT, compose, setup


def inspect(service):
    result = compose('ps', '-q', service, capture=True)
    if not result.stdout.strip():
        raise RuntimeError('Start the lab with python3 lab.py up first')
    return json.loads(subprocess.check_output(['docker', 'inspect', result.stdout.strip()], text=True))[0]


class ContainerBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = inspect('agent')
        cls.database = inspect('db')
        cls.gateway = inspect('gateway')
        cls.outputs = []

    @classmethod
    def tearDownClass(cls):
        logs = compose('logs', '--no-color', 'agent', 'gateway', capture=True)
        result = setup('scan', capture=True, data='\n'.join(cls.outputs + [logs.stdout, logs.stderr]))
        if result.returncode:
            raise AssertionError('A protected canary or credential appeared in agent-visible output/logs')

    def agent_exec(self, *arguments):
        result = compose('exec', '-T', 'agent', *arguments, capture=True, timeout=20)
        self.outputs.extend([result.stdout, result.stderr])
        return result

    def api(self, path, *arguments):
        result = self.agent_exec('python3', '/opt/agent/client.py', path, *arguments)
        self.assertEqual(result.returncode, 0, 'API client could not execute')
        return json.loads(result.stdout)

    def test_non_root_capabilities_and_no_new_privileges(self):
        result = self.agent_exec('python3', '-c', '''import json,os
s=dict(line.split(":",1) for line in open("/proc/self/status") if ":" in line)
print(json.dumps({"uid":os.getuid(),"capabilities":s["CapEff"].strip(),"no_new_privs":s["NoNewPrivs"].strip()}))''')
        self.assertEqual(result.returncode, 0)
        value = json.loads(result.stdout)
        self.assertEqual(value['uid'], 10001)
        self.assertEqual(int(value['capabilities'], 16), 0)
        self.assertEqual(value['no_new_privs'], '1')
        self.assertFalse(self.agent['HostConfig']['Privileged'])
        self.assertLessEqual(self.agent['HostConfig']['PidsLimit'], 128)

    def test_cannot_sudo_or_write_root_filesystem(self):
        result = self.agent_exec('sh', '-c', 'sudo -n id -u')
        self.assertNotEqual(result.returncode, 0)
        result = self.agent_exec('python3', '-c', 'open("/workspace/unauthorized", "w").write("x")')
        self.assertNotEqual(result.returncode, 0)
        result = self.agent_exec('python3', '-c', 'open("/tmp/allowed", "w").write("x")')
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.agent['HostConfig']['ReadonlyRootfs'])

    def test_mounts_and_environment_have_no_privileged_paths_or_credentials(self):
        volumes = [mount for mount in self.agent['Mounts'] if mount['Type'] != 'tmpfs']
        self.assertEqual(len(volumes), 1)
        self.assertEqual(volumes[0]['Type'], 'volume')
        self.assertEqual(volumes[0]['Destination'], '/run/agent')
        self.assertFalse(volumes[0]['RW'])
        self.assertEqual(self.agent['HostConfig']['PidMode'], '')
        self.assertFalse(self.agent['HostConfig']['Devices'])
        result = self.agent_exec('python3', '-c', '''import json,os
from pathlib import Path
paths=["/var/run/docker.sock","/run/secrets/db_admin","/run/gateway/connection.json","/state/config.json","/workspace/.env.production","/root/.ssh","/root/.codex/auth.json"]
print(json.dumps({"environment":dict(os.environ),"unexpected_paths":[p for p in paths if os.access(p,os.R_OK)]}))''')
        self.assertEqual(result.returncode, 0)
        value = json.loads(result.stdout)
        self.assertFalse(value['unexpected_paths'])
        forbidden = ('POSTGRES_PASSWORD', 'ADMIN_DSN', 'DATABASE_URL', 'OPENAI_API_KEY', 'CODEX_API_KEY', 'ANTHROPIC_API_KEY')
        self.assertFalse(set(forbidden) & value['environment'].keys())

    def test_database_network_isolation_by_name_and_actual_ip(self):
        agent_networks = set(self.agent['NetworkSettings']['Networks'])
        database_networks = self.database['NetworkSettings']['Networks']
        self.assertFalse(agent_networks & set(database_networks))
        self.assertTrue(agent_networks & set(self.gateway['NetworkSettings']['Networks']))
        self.assertTrue(set(database_networks) & set(self.gateway['NetworkSettings']['Networks']))
        self.assertFalse(self.database['HostConfig']['PortBindings'])
        for network in agent_networks | set(database_networks):
            config = json.loads(subprocess.check_output(['docker', 'network', 'inspect', network], text=True))[0]
            self.assertTrue(config['Internal'])
        # Test actual TCP, including an IP obtained by the trusted presenter.
        targets = ['db'] + [network['IPAddress'] for network in database_networks.values()]
        for target in targets:
            with self.subTest(target=target):
                result = self.agent_exec('python3', '-c',
                    'import socket,sys; socket.create_connection((sys.argv[1],5432),timeout=2)', target)
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.api('/projects')['status'], 200)

    def test_direct_internet_route_is_blocked(self):
        result = self.agent_exec('python3', '-c',
            'import socket; socket.create_connection(("1.1.1.1",443),timeout=2)')
        self.assertNotEqual(result.returncode, 0)

    def test_real_codex_cli_is_installed(self):
        result = self.agent_exec('codex', '--version')
        self.assertEqual(result.returncode, 0)
        self.assertIn('0.163.0', result.stdout)

    def test_authentication_is_required(self):
        self.assertEqual(self.api('/projects', '--anonymous')['status'], 401)
        self.assertEqual(self.api('/me')['body'], {'actor': 'workshop-agent', 'company_id': 1})

    def test_approved_average_is_available(self):
        response = self.api('/companies/1/salary-summary')
        self.assertEqual(response['status'], 200)
        self.assertEqual(response['body']['company_id'], 1)
        self.assertEqual(float(response['body']['average_salary_eur']), 4000)
        self.assertEqual(set(response['body']), {'company_id', 'employee_count', 'average_salary_eur'})

    def test_forbidden_salary_and_other_company_are_denied(self):
        for path in ['/employees/9001/salary', '/companies/2/salary-summary', '/admin/users']:
            with self.subTest(path=path):
                response = self.api(path)
                self.assertEqual(response['status'], 403)
                self.assertTrue(response['request_id'])

    def test_spoofed_identity_headers_do_not_grant_access(self):
        response = self.api('/companies/2/salary-summary', '--header', 'X-User=admin', '--header', 'X-Account-ID=admin')
        self.assertEqual(response['status'], 403)
        self.assertEqual(self.api('/employees/9001/salary?user_id=admin')['status'], 400)

    def test_no_sql_proxy_or_mutation_api(self):
        self.assertEqual(self.api('/sql', '--method', 'POST')['status'], 405)
        self.assertEqual(self.api('/proxy?url=http://db:5432')['status'], 400)


spec = importlib.util.spec_from_file_location('broker', ROOT / 'model-broker' / 'broker.py')
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.forwarded = []

        def upstream(request, timeout):
            self.forwarded.append(request)
            class Response(io.BytesIO):
                status = 200
                headers = {'Content-Type': 'text/event-stream'}
            return Response(b'event: response.completed\ndata: {"type":"response.completed"}\n\n')

        handler = broker.handler_factory('local-token', 'upstream-only-key', 'test-model', limit=1, opener=upstream)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def call(self, path='/v1/responses', token='local-token', **overrides):
        body = {'model': 'test-model', 'input': 'Synthetic exercise', 'stream': True, **overrides}
        request = Request(f'http://127.0.0.1:{self.server.server_port}{path}', data=json.dumps(body).encode(),
            headers={'Authorization': 'Bearer ' + token, 'X-Untrusted': 'do-not-forward'})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read()

    def test_upstream_key_is_injected_and_stream_is_preserved(self):
        status, data = self.call(max_output_tokens=99999, store=True)
        self.assertEqual(status, 200)
        self.assertIn(b'response.completed', data)
        request = self.forwarded[0]
        self.assertEqual(request.full_url, 'https://api.openai.com/v1/responses')
        self.assertEqual(request.get_header('Authorization'), 'Bearer upstream-only-key')
        self.assertIsNone(request.get_header('X-untrusted'))
        body = json.loads(request.data)
        self.assertFalse(body['store'])
        self.assertEqual(body['max_output_tokens'], 4096)
        self.assertNotIn(b'upstream-only-key', data)

    def test_wrong_token_is_rejected(self):
        self.assertEqual(self.call(token='forged')[0], 401)
        self.assertFalse(self.forwarded)

    def test_arbitrary_endpoint_is_rejected(self):
        self.assertEqual(self.call(path='/v1/files')[0], 404)
        self.assertFalse(self.forwarded)

    def test_other_model_is_rejected(self):
        self.assertEqual(self.call(model='another-model')[0], 400)
        self.assertFalse(self.forwarded)

    def test_upstream_web_tool_is_rejected(self):
        self.assertEqual(self.call(tools=[{'type': 'web_search'}])[0], 400)
        self.assertFalse(self.forwarded)

    def test_namespaced_local_tools_are_supported(self):
        self.assertEqual(self.call(tools=[{'type': 'namespace', 'name': 'functions',
            'tools': [{'type': 'function', 'name': 'exec_command'}]}])[0], 200)

    def test_namespace_cannot_hide_upstream_tools(self):
        self.assertEqual(self.call(tools=[{'type': 'namespace', 'name': 'functions',
            'tools': [{'type': 'web_search'}]}])[0], 400)
        self.assertFalse(self.forwarded)

    def test_request_budget_is_enforced(self):
        self.assertEqual(self.call()[0], 200)
        self.assertEqual(self.call()[0], 429)
        self.assertEqual(len(self.forwarded), 1)
