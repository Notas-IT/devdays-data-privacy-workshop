"""Check output safety and batch boundaries with synthetic input only."""

from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from samples import event, sensitive_values
from starter import MAX_RECORD_BYTES, process_snapshot, run_batch, sanitise


class ProcessorTest(unittest.TestCase):
    def process(self, content, size=None):
        output, errors = StringIO(), StringIO()
        process_snapshot(BytesIO(content), len(content) if size is None else size,
                         'hr', output, errors)
        return output.getvalue(), errors.getvalue()

    def test_all_fixture_pii_is_removed_and_operational_metadata_survives(self):
        records = [event(service, sequence) for service in ('hr', 'billing') for sequence in range(2)]
        for record in records:
            clean = sanitise(record, 'hr' if record['event'] == 'salary_export' else 'billing')
            rendered = json.dumps(clean, ensure_ascii=False)
            for sensitive in sensitive_values():
                self.assertNotIn(sensitive, rendered)
            self.assertEqual(clean['event'], record['event'])
            self.assertEqual(clean['level'], 'INFO')
            self.assertEqual(clean['sequence'], record['sequence'])
            self.assertEqual(clean['message'], '[REDACTED]')

    def test_unfamiliar_payloads_keys_arrays_and_messages_are_not_exposed(self):
        record = {'event': 'invoice_created', 'level': 'info', 'sequence': 42,
                  'source_service': 'forged', 'timestamp': '2026-11-11T12:00:00Z',
                  'message': 'Unrecognised person and financial details',
                  'unknown': [{'unexpected': {'private@example.invalid': 'secret'}}],
                  'private@example.invalid': 123456}
        self.assertEqual(sanitise(record, 'billing'), {
            'source_service': 'billing', 'level': 'INFO', 'event': 'invoice_created',
            'sequence': 42, 'timestamp': '2026-11-11T12:00:00+00:00', 'message': '[REDACTED]'})

    def test_invalid_operational_fields_are_omitted(self):
        self.assertEqual(sanitise({'level': 'private@example.invalid', 'event': 'phone_061234567',
            'sequence': True, 'timestamp': 'a private address'}, 'hr'), {'source_service': 'hr'})

    def test_malformed_records_do_not_leak_and_next_valid_record_is_processed(self):
        content = (b'{"secret": "private@example.invalid"\n'
                   b'\xff\n[]\n{"x": NaN}\n{"x": 1, "x": 2}\n'
                   b'{"event":"salary_export","sequence":7}\n')
        output, errors = self.process(content)
        self.assertEqual(json.loads(output)['sequence'], 7)
        self.assertEqual(errors.count('skipped malformed record'), 5)
        self.assertNotIn('private@example.invalid', output + errors)

    def test_appended_records_are_excluded_from_the_initial_snapshot(self):
        first = b'{"sequence":1}\n'
        output, _ = self.process(first + b'{"sequence":2}\n', size=len(first))
        self.assertEqual([json.loads(line)['sequence'] for line in output.splitlines()], [1])

    def test_oversized_record_is_skipped_and_processing_resumes(self):
        output, errors = self.process(b'x' * (MAX_RECORD_BYTES + 20) + b'\n{"sequence":3}\n')
        self.assertEqual(json.loads(output)['sequence'], 3)
        self.assertEqual(errors, 'hr: skipped oversized record at line 1\n')

    def test_both_sources_are_read_without_changing_input_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            inputs = [(service, Path(temporary) / f'{service}.jsonl') for service in ('hr', 'billing')]
            originals = []
            for service, path in inputs:
                content = (json.dumps(event(service, 0), ensure_ascii=False) + '\n').encode()
                path.write_bytes(content)
                originals.append(content)
            output, errors = StringIO(), StringIO()
            self.assertEqual(run_batch(inputs, output, errors), 0)
            self.assertEqual([json.loads(line)['source_service'] for line in output.getvalue().splitlines()],
                             ['hr', 'billing'])
            self.assertEqual(errors.getvalue(), '')
            self.assertEqual([path.read_bytes() for _, path in inputs], originals)

    def test_missing_source_is_reported_without_disclosing_path_and_other_source_is_processed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'billing.jsonl'
            path.write_text('{"sequence":9}')
            output, errors = StringIO(), StringIO()
            self.assertEqual(run_batch([('hr', Path(temporary) / 'secret@example.invalid'),
                                        ('billing', path)], output, errors), 1)
            self.assertEqual(errors.getvalue(), 'hr: input unavailable\n')
            self.assertEqual(json.loads(output.getvalue())['sequence'], 9)


if __name__ == '__main__':
    unittest.main()
