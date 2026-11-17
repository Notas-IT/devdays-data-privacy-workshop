"""Verify the running network boundary, including the database's actual IP."""

import errno
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NetworkIsolationTest(unittest.TestCase):
    @classmethod
    def compose(cls, *args):
        return subprocess.run(
            ['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml'), *args],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout

    @classmethod
    def setUpClass(cls):
        cls.services = {}
        for service in ('agent', 'db', 'gateway', 'model-proxy'):
            container = cls.compose('ps', '-q', service).strip()
            if not container:
                raise RuntimeError(f'Start the workshop first: {service} is not running')
            result = subprocess.run(
                ['docker', 'inspect', '--format',
                 '{"host":{{json .HostConfig}},"mounts":{{json .Mounts}},'
                 '"networks":{{json .NetworkSettings.Networks}},'
                 '"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}}}',
                 container], capture_output=True, text=True, check=True, timeout=30,
            )
            cls.services[service] = json.loads(result.stdout)

    def test_network_membership_matches_the_required_boundary(self):
        agent = set(self.services['agent']['networks'])
        database = set(self.services['db']['networks'])
        gateway = set(self.services['gateway']['networks'])
        self.assertEqual(len(agent), 1)
        self.assertEqual(len(database), 1)
        self.assertTrue(next(iter(agent)).endswith('_agent_net'))
        self.assertTrue(next(iter(database)).endswith('_db_net'))
        self.assertTrue(agent.isdisjoint(database))
        self.assertEqual(gateway, agent | database)
        proxy = set(self.services['model-proxy']['networks'])
        self.assertEqual(len(proxy), 2)
        self.assertTrue(agent.issubset(proxy))
        self.assertTrue(proxy.isdisjoint(database))
        self.assertTrue(next(iter(proxy - agent)).endswith('_outbound_net'))

    def test_both_networks_are_internal(self):
        for network in self.services['gateway']['networks']:
            with self.subTest(network=network):
                result = subprocess.run(
                    ['docker', 'network', 'inspect', '--format', '{{json .Internal}}', network],
                    capture_output=True, text=True, check=True, timeout=30,
                )
                self.assertIs(json.loads(result.stdout), True)

    def test_no_service_publishes_ports(self):
        for name, service in self.services.items():
            with self.subTest(service=name):
                self.assertFalse(service['host']['PortBindings'])
                self.assertFalse(service['host']['PublishAllPorts'])

    def test_database_and_gateway_are_healthy(self):
        for name in ('db', 'gateway', 'model-proxy'):
            with self.subTest(service=name):
                self.assertEqual(self.services[name]['health'], 'healthy')

    def test_direct_database_connections_are_blocked_by_name_and_ip(self):
        address = next(iter(self.services['db']['networks'].values()))['IPAddress']
        self.assertTrue(address, 'The database must have an address for the IP bypass probe')
        result = json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, socket, sys
outcomes = []
for host in ('db', sys.argv[1]):
    try:
        connection = socket.create_connection((host, 5432), timeout=2)
    except OSError:
        outcomes.append({'host': host, 'connected': False})
    else:
        connection.close()
        outcomes.append({'host': host, 'connected': True})
print(json.dumps(outcomes))
''', address))
        self.assertEqual(result, [{'host': 'db', 'connected': False},
                                  {'host': address, 'connected': False}])

    def test_agent_has_no_database_credentials_or_gateway_config(self):
        result = json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, os
from pathlib import Path
names = ('DATABASE_URL', 'PGPASSWORD', 'POSTGRES_PASSWORD', 'DB_PASSWORD')
print(json.dumps({'database_environment': [name for name in names if os.environ.get(name)],
                  'gateway_config_visible': Path('/run/gateway/connection.json').exists()}))
'''))
        self.assertEqual(result, {'database_environment': [], 'gateway_config_visible': False})

    def test_gateway_configuration_volume_is_read_only(self):
        mounts = [mount for mount in self.services['gateway']['mounts']
                  if mount['Destination'] == '/run/gateway']
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0]['Type'], 'volume')
        self.assertFalse(mounts[0]['RW'])
        result = json.loads(self.compose('exec', '-T', 'gateway', 'python', '-c', '''
import json, os
write_errno = 0
try:
    descriptor = os.open('/run/gateway/connection.json', os.O_WRONLY | os.O_APPEND)
except OSError as error:
    write_errno = error.errno
else:
    os.close(descriptor)
print(json.dumps({'read_only_mount': bool(os.statvfs('/run/gateway').f_flag & os.ST_RDONLY),
                  'write_errno': write_errno}))
'''))
        self.assertTrue(result['read_only_mount'])
        self.assertIn(result['write_errno'], (errno.EROFS, errno.EACCES))

    def test_only_model_proxy_has_outbound_network_access(self):
        agent = set(self.services['agent']['networks'])
        outbound = set(self.services['model-proxy']['networks']) - agent
        self.assertEqual(len(outbound), 1)
        network = next(iter(outbound))
        result = subprocess.run(
            ['docker', 'network', 'inspect', '--format', '{{json .Internal}}', network],
            capture_output=True, text=True, check=True, timeout=30,
        )
        self.assertIs(json.loads(result.stdout), False)
        for name in ('agent', 'db', 'gateway'):
            self.assertNotIn(network, self.services[name]['networks'])

    def test_agent_cannot_connect_directly_to_openai(self):
        address = self.compose('exec', '-T', 'model-proxy', 'python', '-c',
                               "import socket; print(socket.gethostbyname('api.openai.com'))").strip()
        result = self.compose('exec', '-T', 'agent', 'python', '-c', '''
import socket, sys
try:
    connection = socket.create_connection((sys.argv[1], 443), timeout=2)
except OSError:
    print('blocked')
else:
    connection.close()
    print('connected')
''', address)
        self.assertEqual(result.strip(), 'blocked')

    def test_model_proxy_health_and_authentication_are_reachable(self):
        result = json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, os
from urllib.request import Request, urlopen
from urllib.error import HTTPError
base = os.environ['MODEL_PROXY_URL']
with urlopen(base + '/health', timeout=5) as response:
    healthy = json.load(response)
request = Request(base + '/v1/responses', data=b'{}', headers={'Content-Type': 'application/json'})
try:
    with urlopen(request, timeout=5) as response:
        unauthorized_status = response.status
except HTTPError as error:
    unauthorized_status = error.code
print(json.dumps({'health': healthy, 'unauthorized_status': unauthorized_status}))
'''))
        self.assertEqual(result, {'health': {'status': 'ok', 'configured': True},
                                  'unauthorized_status': 401})

    def test_deployed_model_broker_policy_and_rejections(self):
        result = self.compose('exec', '-T', 'agent', 'python', 'check_model_proxy.py')
        self.assertIn('PASS: model broker checks passed; no paid model request was sent', result)
