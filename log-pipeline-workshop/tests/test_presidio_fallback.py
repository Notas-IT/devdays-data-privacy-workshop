"""Exercise fallback output and HTTP failures without loading an NLP model."""

from http.server import ThreadingHTTPServer
from io import StringIO
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from presidio_server import make_handler, parse_batch, sanitise_fallback
from samples import event, sensitive_values


class FakeAnalyzer:
    def analyze(self, **kwargs):
        self.text = kwargs['text']
        return [SimpleNamespace(entity_type='EMAIL_ADDRESS')]


class FakeAnonymizer:
    def anonymize(self, **kwargs):
        self.text = kwargs['text']
        return SimpleNamespace(text='[REDACTED]')


class FallbackTest(unittest.TestCase):
    def test_analyzes_nested_payload_but_never_outputs_original_values(self):
        analyzer, anonymizer = FakeAnalyzer(), FakeAnonymizer()
        record = {**event('hr', 4), 'source_service': 'hr'}
        clean = sanitise_fallback(record, analyzer, anonymizer)
        self.assertIn(record['debug']['customer']['email'], analyzer.text)
        self.assertEqual(analyzer.text, anonymizer.text)
        self.assertEqual(clean['processing_path'], 'presidio')
        self.assertEqual(clean['presidio_detection_count'], 1)
        for value in sensitive_values():
            self.assertNotIn(value, json.dumps(clean, ensure_ascii=False))

    def test_detector_miss_does_not_release_undetected_private_text(self):
        analyzer = SimpleNamespace(analyze=lambda **kwargs: [])
        clean = sanitise_fallback({'message': 'Unfamiliar secret', 'payload': ['Other secret']},
                                  analyzer, FakeAnonymizer())
        self.assertEqual(clean['message'], '[REDACTED]')
        self.assertNotIn('secret', json.dumps(clean))

    def test_invalid_batches_are_rejected(self):
        for body in (b'[]', b'{"secret":NaN}', b'{"a":1,"a":2}', b'\xff', b'not-json'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_batch(body)

    def test_http_health_success_and_failure_with_no_raw_output_on_failure(self):
        analyzer, output = FakeAnalyzer(), StringIO()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(analyzer, FakeAnonymizer(), output))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base + '/health') as response:
                self.assertEqual(response.status, 200)
            body = json.dumps({**event('hr', 4), 'source_service': 'hr'}).encode()
            with urlopen(Request(base + '/sanitize', data=body)) as response:
                self.assertEqual(json.load(response), {'accepted': 1})
            self.assertEqual(json.loads(output.getvalue())['processing_path'], 'presidio')
            before = output.getvalue()
            def fail(**kwargs):
                raise RuntimeError('private@example.invalid')
            analyzer.analyze = fail
            with self.assertRaises(HTTPError) as failure:
                urlopen(Request(base + '/sanitize', data=body))
            self.assertEqual(failure.exception.code, 503)
            self.assertNotIn(b'private@example.invalid', failure.exception.read())
            self.assertEqual(output.getvalue(), before)
            with self.assertRaises(HTTPError) as malformed:
                urlopen(Request(base + '/sanitize', data=b'private@example.invalid'))
            self.assertEqual(malformed.exception.code, 400)
            self.assertNotIn(b'private@example.invalid', malformed.exception.read())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
