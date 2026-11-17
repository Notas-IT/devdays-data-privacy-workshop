"""Private Fluent Bit fallback. No raw request or exception content is logged."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
import threading

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from starter import invalid_constant, sanitise, unique_fields


MAX_BODY = 1024 * 1024
MAX_RECORDS = 500


def build_analyzer():
    analyzer = AnalyzerEngine()
    for entity, pattern in [
        ('LT_NATIONAL_ID', r'\b[1-6][0-9]{10}\b'),
        ('LT_PHONE', r'(?<!\w)(?:\+370|00370|0|8)[ ()-]*6(?:[ ()-]*\d){7}(?!\d)'),
        ('FINANCIAL_AMOUNT', r'\b\d+(?:[.,]\d+)?\s*(?:EUR|eur|€)'),
    ]:
        analyzer.registry.add_recognizer(PatternRecognizer(supported_entity=entity,
            patterns=[Pattern(name=entity, regex=pattern, score=0.85)]))
    return analyzer


def sanitise_fallback(record, analyzer, anonymizer):
    # Analyse the whole record so nested objects, arrays and unexpected keys are examined.
    text = json.dumps(record, ensure_ascii=False, allow_nan=False)
    findings = analyzer.analyze(text=text, language='en', score_threshold=0.5)
    anonymizer.anonymize(text=text, analyzer_results=findings,
        operators={'DEFAULT': OperatorConfig('replace', {'new_value': '[REDACTED]'})})
    service = record.get('source_service')
    if service not in {'hr', 'billing', 'test'}:
        service = 'unknown'
    clean = sanitise(record, service)
    # Detection is not proof that every secret was found. Keep the existing
    # allowlist and whole-message redaction instead of publishing remaining text.
    clean['processing_path'] = 'presidio'
    clean['presidio_detection_count'] = len(findings)
    clean['presidio_entities'] = sorted({item.entity_type for item in findings})
    return clean


def parse_batch(body):
    records = [json.loads(line, object_pairs_hook=unique_fields, parse_constant=invalid_constant)
               for line in body.decode('utf-8').splitlines() if line.strip()]
    if not records or len(records) > MAX_RECORDS or any(not isinstance(item, dict) for item in records):
        raise ValueError('Invalid record batch')
    return records


def make_handler(analyzer, anonymizer, output=sys.stdout):
    lock = threading.Lock()
    counters = {'requests': 0, 'records': 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/health':
                self.respond(200, {'status': 'ready'})
            elif self.path == '/metrics':
                with lock:
                    self.respond(200, dict(counters))
            else:
                self.respond(404, {'error': 'not found'})

        def do_POST(self):
            if self.path != '/sanitize':
                self.respond(404, {'error': 'not found'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_BODY:
                    self.respond(413, {'error': 'invalid request size'})
                    return
                self.connection.settimeout(10)
                body = self.rfile.read(size)
                if len(body) != size:
                    raise ValueError('Incomplete request')
                records = parse_batch(body)
            except (ValueError, UnicodeError, RecursionError, OSError):
                self.respond(400, {'error': 'invalid log batch'})
                return
            try:
                with lock:
                    clean = [sanitise_fallback(record, analyzer, anonymizer) for record in records]
                    for record in clean:
                        print(json.dumps(record, ensure_ascii=False, allow_nan=False), file=output, flush=True)
                    counters['requests'] += 1
                    counters['records'] += len(clean)
            except Exception:
                # Fluent Bit retries; raw logs never become an error response or stdout fallback.
                self.respond(503, {'error': 'sanitisation unavailable'})
                return
            self.respond(200, {'accepted': len(clean)})

    return Handler


def main():
    analyzer = build_analyzer()
    ThreadingHTTPServer(('0.0.0.0', 8080), make_handler(analyzer, AnonymizerEngine())).serve_forever()


if __name__ == '__main__':
    main()
