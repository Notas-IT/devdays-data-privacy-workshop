"""Check the running container's settings, kernel state and retained access."""

import errno
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AgentContainerSecurityTest(unittest.TestCase):
    @classmethod
    def compose(cls, *args):
        return subprocess.run(
            ['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml'), *args],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout

    @classmethod
    def setUpClass(cls):
        container = cls.compose('ps', '-q', 'agent').strip()
        if not container:
            raise RuntimeError('Start the workshop with docker compose up -d --build --wait')
        # Inspect only selected fields; never fetch or print environment secrets.
        result = subprocess.run(
            ['docker', 'inspect', '--format',
             '{"user":{{json .Config.User}},"host":{{json .HostConfig}},'
             '"mounts":{{json .Mounts}},"networks":{{json .NetworkSettings.Networks}}}', container],
            capture_output=True, text=True, check=True, timeout=30,
        )
        cls.container = json.loads(result.stdout)
        cls.status = json.loads(cls.compose('exec', '-T', 'agent', 'python', '-c', '''
import json
from pathlib import Path
def status(path):
    return dict(line.split(':', 1) for line in Path(path).read_text().splitlines() if ':' in line)
print(json.dumps({'init': status('/proc/1/status'), 'exec': status('/proc/self/status')}))
'''))

    def test_uid_and_gid_are_1001(self):
        self.assertEqual(self.container['user'], '1001:1001')
        for process, status in self.status.items():
            with self.subTest(process=process):
                self.assertEqual(status['Uid'].split(), ['1001'] * 4)
                self.assertEqual(status['Gid'].split(), ['1001'] * 4)

    def test_all_linux_capabilities_are_dropped(self):
        self.assertIn('ALL', self.container['host']['CapDrop'])
        self.assertFalse(self.container['host']['CapAdd'])
        for process, status in self.status.items():
            for name in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'):
                with self.subTest(process=process, capability_set=name):
                    self.assertEqual(int(status[name].strip(), 16), 0)

    def test_no_new_privileges_is_enforced(self):
        options = self.container['host']['SecurityOpt']
        self.assertTrue(any(item.split(':')[0] == 'no-new-privileges' for item in options))
        for process, status in self.status.items():
            with self.subTest(process=process):
                self.assertEqual(status['NoNewPrivs'].strip(), '1')

    def test_privileged_mode_is_disabled(self):
        self.assertFalse(self.container['host']['Privileged'])

    def write_probe(self, directory):
        return json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, sys, tempfile
from pathlib import Path
try:
    with tempfile.NamedTemporaryFile(dir=sys.argv[1]) as output:
        output.write(b'workshop-write-check')
        output.flush()
        assert Path(output.name).read_bytes() == b'workshop-write-check'
except OSError as error:
    print(json.dumps({'written': False, 'errno': error.errno}))
else:
    print(json.dumps({'written': True}))
''', directory))

    def test_root_filesystem_is_read_only(self):
        self.assertTrue(self.container['host']['ReadonlyRootfs'])
        # /var/tmp is writable by ordinary users on the original image.
        result = self.write_probe('/var/tmp')
        self.assertEqual(result, {'written': False, 'errno': errno.EROFS})

    def test_workspace_write_is_denied(self):
        mounts = [mount for mount in self.container['mounts']
                  if mount['Destination'] == '/workspace']
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0]['Type'], 'bind')
        self.assertEqual(Path(mounts[0]['Source']).resolve(), (ROOT / 'workspace').resolve())
        self.assertFalse(mounts[0]['RW'])
        self.assertEqual(self.write_probe('/workspace'),
                         {'written': False, 'errno': errno.EROFS})

    def test_tmp_write_succeeds_on_temporary_mount(self):
        self.assertIn('/tmp', self.container['host']['Tmpfs'])
        self.assertEqual(self.write_probe('/tmp'), {'written': True})

    def test_agent_home_write_succeeds_on_temporary_mount(self):
        self.assertIn('/home/agent', self.container['host']['Tmpfs'])
        self.assertEqual(self.write_probe('/home/agent'), {'written': True})

    def test_credential_mount_is_read_only(self):
        mounts = [mount for mount in self.container['mounts']
                  if mount['Destination'] == '/run/agent']
        self.assertEqual(len(mounts), 1)
        self.assertFalse(mounts[0]['RW'])
        self.assertEqual(mounts[0]['Type'], 'volume')
        result = json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, os
write_errno = 0
try:
    descriptor = os.open('/run/agent/access.json', os.O_WRONLY | os.O_APPEND)
except OSError as error:
    write_errno = error.errno
else:
    os.close(descriptor)
print(json.dumps({'read_only_mount': bool(os.statvfs('/run/agent').f_flag & os.ST_RDONLY),
                  'write_errno': write_errno}))
'''))
        self.assertTrue(result['read_only_mount'])
        self.assertIn(result['write_errno'], (errno.EROFS, errno.EACCES))

    def test_database_access_through_gateway_is_available(self):
        result = json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, os
from pathlib import Path
from urllib.request import urlopen
from urllib.request import Request
token = json.loads(Path('/run/identity/access.json').read_text())['gateway_token']
request = Request(os.environ['GATEWAY_URL'] + '/projects', headers={'Authorization': 'Bearer ' + token})
with urlopen(request, timeout=5) as response:
    print(response.read().decode())
'''))
        self.assertEqual(result, {'items': [
            {'project_id': 1, 'title': 'Conference schedule'},
            {'project_id': 2, 'title': 'Workshop materials'},
        ]})

    def test_codex_is_installed(self):
        result = self.compose('exec', '-T', 'agent', 'codex', '--version')
        self.assertIn('codex', result.lower())

    def test_agent_has_only_local_proxy_credentials(self):
        result = json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, os
from pathlib import Path
access = json.loads(Path('/run/agent/access.json').read_text())
names = ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPEN_AI_API', 'OPEN_AI_API_KEY')
print(json.dumps({'upstream_keys_present': [name for name in names if os.environ.get(name)],
                  'local_proxy_token_present': bool(access.get('model_token')),
                  'credential_fields': sorted(access),
                  'old_credential_file_present': Path('/run/credentials/agent.env').exists()}))
'''))
        self.assertEqual(result, {'upstream_keys_present': [], 'local_proxy_token_present': True,
                                  'credential_fields': ['model', 'model_token'],
                                  'old_credential_file_present': False})

    def test_only_required_host_paths_are_mounted(self):
        allowed = {'/workspace', '/run/agent', '/run/identity'}
        host_mounts = [mount for mount in self.container['mounts']
                       if mount['Type'] != 'tmpfs']
        self.assertEqual(len(host_mounts), len(allowed))
        for mount in host_mounts:
            destination = mount['Destination']
            with self.subTest(destination=destination):
                self.assertIn(destination, allowed)
                if destination == '/workspace':
                    self.assertEqual(mount['Type'], 'bind')
                    self.assertEqual(Path(mount['Source']).resolve(), (ROOT / 'workspace').resolve())
                else:
                    self.assertEqual(mount['Type'], 'volume')
                    suffix = '_agent_config' if destination == '/run/agent' else '_agent_identity'
                    self.assertTrue(mount['Name'].endswith(suffix))
                self.assertFalse(mount['RW'])

    def test_gateway_identity_credential_is_read_only(self):
        result = json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import errno, json, os
from pathlib import Path
path = Path('/run/identity/access.json')
access = json.loads(path.read_text())
try:
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
except OSError as error:
    denied = error.errno in (errno.EROFS, errno.EACCES)
else:
    os.close(descriptor)
    denied = False
print(json.dumps({'fields': sorted(access), 'token_present': bool(access.get('gateway_token')),
                  'read_only': bool(os.statvfs(path).f_flag & os.ST_RDONLY), 'write_denied': denied}))
'''))
        self.assertEqual(result, {'fields': ['gateway_token'], 'token_present': True,
                                  'read_only': True, 'write_denied': True})

    def test_host_namespaces_and_devices_are_not_shared(self):
        host = self.container['host']
        self.assertIn(host['PidMode'], ('', 'private'))
        self.assertEqual(host['IpcMode'], 'private')
        self.assertIn(host['UTSMode'], ('', 'private'))
        self.assertNotIn(host['NetworkMode'], ('host', 'service:host'))
        self.assertFalse(host['NetworkMode'].startswith('container:'))
        self.assertFalse(host['Devices'])
        self.assertFalse(host['DeviceRequests'])

    def test_docker_and_ssh_sockets_are_unavailable(self):
        result = json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, os
from pathlib import Path
paths = ('/var/run/docker.sock', '/run/docker.sock',
         '/run/host-services/ssh-auth.sock', '/run/podman/podman.sock')
print(json.dumps({
    'socket_paths_present': [path for path in paths if Path(path).exists()],
    'forwarded_environment': [name for name in ('SSH_AUTH_SOCK', 'DOCKER_HOST',
                              'DOCKER_CONTEXT', 'DOCKER_CERT_PATH') if os.environ.get(name)],
    'workspace_has_host_env': Path('/workspace/.env').exists(),
    'workspace_has_git_metadata': Path('/workspace/.git').exists(),
}))
'''))
        self.assertEqual(result, {'socket_paths_present': [], 'forwarded_environment': [],
                                  'workspace_has_host_env': False,
                                  'workspace_has_git_metadata': False})

    def test_host_file_outside_workspace_cannot_be_read(self):
        # Make a harmless real host file; clean it up even when a check fails.
        with tempfile.TemporaryDirectory(prefix='.agent-host-probe-', dir=ROOT.parent) as directory:
            fixture = Path(directory) / 'host-only.txt'
            fixture.write_text('Synthetic host-only test fixture.\n')
            self.assertTrue(fixture.is_file())
            candidates = [str(fixture), '/host' + str(fixture),
                          '/proc/1/root' + str(fixture),
                          f'/workspace/../{fixture.parent.name}/{fixture.name}',
                          f'/workspace/../../{fixture.parent.name}/{fixture.name}']
            result = json.loads(self.compose('exec', '-T', 'agent', 'python', '-c', '''
import json, sys
from pathlib import Path
readable = []
for name in json.loads(sys.argv[1]):
    try:
        Path(name).read_bytes()
    except (FileNotFoundError, PermissionError, NotADirectoryError):
        continue
    readable.append(name)
print(json.dumps(readable))
''', json.dumps(candidates)))
            self.assertEqual(result, [], 'The agent must not read the host-only fixture')


if __name__ == '__main__':
    unittest.main()
