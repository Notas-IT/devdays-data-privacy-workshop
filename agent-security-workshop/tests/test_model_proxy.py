"""Exercise the proxy with a fake upstream; these tests never spend API tokens."""

from http.server import ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
import http.client
import importlib.util
import io
import json
from pathlib import Path
import threading
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


path = Path(__file__).resolve().parents[1] / 'model-broker' / 'broker.py'
spec = importlib.util.spec_from_file_location('workshop_model_broker', path)
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)


class ModelProxyTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Type': 'application/json'}

        def upstream(request, timeout):
            self.calls.append(request)
            return Response(b'{"id":"fake-response"}')

        self.upstream = upstream
        self.budget = broker.MemoryBudget(1)
        handler = broker.handler_factory('local-token', 'upstream-test-key', 'test-model',
                                         limit=1, opener=upstream, budget=self.budget)
        self.base = self.start_server(handler)

    def start_server(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        self.addCleanup(self.stop_server, server, thread)
        return f'http://127.0.0.1:{server.server_port}'

    def stop_server(self, server, thread):
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    def request(self, body=None, *, token='local-token', path='/v1/responses', method='POST', headers=None, base=None):
        values = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
        values.update(headers or {})
        request = Request((base or self.base) + path, method=method,
                          data=json.dumps(body if body is not None else {'model': 'test-model', 'input': 'hello'}).encode(),
                          headers=values)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_only_local_token_authenticates(self):
        status, _ = self.request(token='wrong-token')
        self.assertEqual(status, 401)
        self.assertEqual(self.calls, [])

    def test_upstream_key_is_injected_only_for_fixed_responses_endpoint(self):
        status, result = self.request({'model': 'test-model', 'input': 'hello',
                                       'max_output_tokens': 10000, 'store': True,
                                       'tools': [{'type': 'function', 'name': 'local_shell'}]})
        self.assertEqual((status, result), (200, {'id': 'fake-response'}))
        self.assertEqual(len(self.calls), 1)
        call = self.calls[0]
        self.assertEqual(call.full_url, 'https://api.openai.com/v1/responses')
        self.assertEqual(call.get_header('Authorization'), 'Bearer upstream-test-key')
        body = json.loads(call.data)
        self.assertFalse(body['store'])
        self.assertEqual(body['max_output_tokens'], 4096)

    def test_other_models_and_hosted_tools_are_rejected(self):
        for body in ({'model': 'other-model'},
                     {'model': 'test-model', 'tools': [{'type': 'web_search'}]}):
            with self.subTest(body=body):
                self.assertEqual(self.request(body)[0], 400)
        self.assertEqual(self.calls, [])

    def test_arbitrary_endpoints_and_connect_are_rejected(self):
        self.assertEqual(self.request(path='/v1/models')[0], 404)
        self.assertEqual(self.request(path='/', method='CONNECT')[0], 405)
        self.assertEqual(self.calls, [])

    def test_request_budget_is_enforced(self):
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request()[0], 429)
        self.assertEqual(len(self.calls), 1)

    def test_invalid_token_types_and_provider_key_do_not_authenticate(self):
        for token in ('upstream-test-key', 'tést', ''):
            with self.subTest(token=token):
                self.assertEqual(self.request(token=token)[0], 401)
        self.assertEqual(self.calls, [])

    def test_output_limits_require_positive_finite_integers(self):
        for maximum in (True, 2.5, '12', None, 0, -1, float('inf'), float('nan')):
            with self.subTest(maximum=maximum):
                self.assertEqual(self.request({'model': 'test-model', 'max_output_tokens': maximum})[0], 400)
        self.assertEqual(self.calls, [])

    def test_compressed_and_oversized_requests_are_rejected(self):
        self.assertEqual(self.request(headers={'Content-Encoding': 'gzip'})[0], 415)
        self.assertEqual(self.request(headers={'Content-Length': str(broker.MAX_REQUEST_BYTES + 1)})[0], 413)
        self.assertEqual(self.calls, [])

    def test_ambiguous_authorization_and_body_framing_are_rejected(self):
        body = b'{"model":"test-model"}'
        cases = [
            ([('Authorization', 'Bearer local-token'), ('Authorization', 'Bearer wrong')], 401),
            ([('Content-Length', str(len(body)))], 400),
            ([('Transfer-Encoding', 'chunked')], 400),
        ]
        for extra, expected in cases:
            with self.subTest(extra=extra):
                connection = http.client.HTTPConnection(urlsplit(self.base).netloc, timeout=5)
                try:
                    connection.putrequest('POST', '/v1/responses')
                    if expected != 401:
                        connection.putheader('Authorization', 'Bearer local-token')
                    connection.putheader('Content-Length', str(len(body)))
                    for name, value in extra:
                        connection.putheader(name, value)
                    connection.endheaders(body)
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                finally:
                    connection.close()
        self.assertEqual(self.calls, [])

    def test_background_work_and_nonboolean_streaming_are_rejected(self):
        for body in ({'model': 'test-model', 'background': True},
                     {'model': 'test-model', 'stream': 'false'},
                     {'model': 'test-model', 'tools': [{'type': 'namespace', 'tools': [{'type': 'web_search'}]}]}):
            with self.subTest(body=body):
                self.assertEqual(self.request(body)[0], 400)
        self.assertEqual(self.calls, [])

    def test_rejected_requests_do_not_consume_the_request_budget(self):
        self.assertEqual(self.request({'model': 'wrong-model'})[0], 400)
        self.assertEqual(self.request(token='wrong-token')[0], 401)
        self.assertEqual(self.budget.snapshot(), 0)
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request()[0], 429)

    def test_policy_is_authenticated_and_contains_no_credentials(self):
        self.assertEqual(self.request(method='GET', path='/policy', token='wrong-token')[0], 401)
        status, policy = self.request(method='GET', path='/policy')
        self.assertEqual(status, 200)
        self.assertEqual(policy['upstream'], broker.UPSTREAM)
        self.assertEqual(policy['model'], 'test-model')
        self.assertEqual(policy['request_limit'], 1)
        self.assertEqual(policy['requests_remaining'], 1)
        self.assertEqual(policy['max_output_tokens'], 4096)
        self.assertNotIn('upstream-test-key', json.dumps(policy))
        self.assertNotIn('local-token', json.dumps(policy))
        self.assertEqual(self.calls, [])

    def test_persistent_budget_survives_a_new_broker_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'usage.sqlite3'
            urls = []
            for _ in range(2):
                budget = broker.SQLiteBudget(path, 1)
                handler = broker.handler_factory('local-token', 'upstream-test-key', 'test-model',
                    limit=1, opener=self.upstream, budget=budget)
                urls.append(self.start_server(handler))
            self.assertEqual(self.request(base=urls[0])[0], 200)
            self.assertEqual(self.request(base=urls[1])[0], 429)
            self.assertEqual(broker.SQLiteBudget(path, 1).snapshot(), 1)
            self.assertEqual(len(self.calls), 1)

    def test_persistent_budget_is_atomic_under_concurrent_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            budget = broker.SQLiteBudget(Path(directory) / 'usage.sqlite3', 3)
            with ThreadPoolExecutor(max_workers=8) as pool:
                allowed = list(pool.map(lambda _: budget.take(), range(20)))
            self.assertEqual(sum(allowed), 3)
            self.assertEqual(budget.snapshot(), 3)

    def test_accounting_failure_blocks_forwarding(self):
        with patch.object(self.budget, 'take', side_effect=OSError('Simulated storage failure')):
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.calls, [])

    def test_provider_errors_are_sanitized_and_still_consume_budget(self):
        def rejected(request, timeout):
            self.calls.append(request)
            raise HTTPError(broker.UPSTREAM, 401, 'Rejected', {}, io.BytesIO(b'private provider metadata'))
        handler = broker.handler_factory('local-token', 'upstream-test-key', 'test-model',
                                         limit=1, opener=rejected)
        base = self.start_server(handler)
        status, body = self.request(base=base)
        self.assertEqual(status, 502)
        self.assertEqual(body['provider_status'], 401)
        self.assertNotIn('private provider metadata', json.dumps(body))
        self.assertNotIn('upstream-test-key', json.dumps(body))
        self.assertEqual(self.request(base=base)[0], 429)
        self.assertEqual(len(self.calls), 1)

    def test_invalid_limits_and_shared_provider_credentials_fail_at_startup(self):
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                broker.handler_factory('local-token', 'upstream-test-key', 'test-model', limit=limit)
        with self.assertRaises(ValueError):
            broker.handler_factory('same-secret', 'same-secret', 'test-model')
        with self.assertRaises(ValueError):
            broker.handler_factory('', 'upstream-test-key', 'test-model')


if __name__ == '__main__':
    unittest.main()
