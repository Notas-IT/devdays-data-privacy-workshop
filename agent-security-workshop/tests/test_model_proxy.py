"""Exercise the proxy with a fake upstream; these tests never spend API tokens."""

from http.server import ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
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

        handler = broker.handler_factory('local-token', 'upstream-test-key', 'test-model',
                                         limit=1, opener=upstream)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, body=None, *, token='local-token', path='/v1/responses', method='POST'):
        request = Request(self.base + path, method=method,
                          data=json.dumps(body or {'model': 'test-model', 'input': 'hello'}).encode(),
                          headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
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


if __name__ == '__main__':
    unittest.main()
