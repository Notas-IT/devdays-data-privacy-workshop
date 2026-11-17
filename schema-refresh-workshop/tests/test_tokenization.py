"""HMAC correctness and live pseudo-prod checks; never print original values or keys."""

import hashlib
import os
import sys
from pathlib import Path
import unittest

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tokenize_pseudo_prod import keyed_digest, load_key, token, tokenize_pseudo_prod, verify_pseudo_prod


class HmacTest(unittest.TestCase):
    def test_rfc_4231_hmac_sha256_vector(self):
        self.assertEqual(keyed_digest(b'\x0b' * 20, b'Hi There'),
            'b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7')

    def test_token_domains_and_keys_are_distinct(self):
        key = b'a' * 32
        self.assertEqual(token('demo@example.com', 'email', key), token('demo@example.com', 'email', key))
        self.assertNotEqual(token('demo@example.com', 'email', key), token('demo@example.com', 'email', b'b' * 32))
        self.assertNotEqual(token('123', 'email', key), token('123', 'national_id', key))


class PseudoProdTokenizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = load_key()
        cls.source = psycopg.connect(os.environ['SOURCE_DSN'], autocommit=True)
        cls.target = psycopg.connect(os.environ['PSEUDO_PROD_DSN'], autocommit=True)

    @classmethod
    def tearDownClass(cls):
        cls.source.close()
        cls.target.close()

    def test_all_identifier_values_match_keyed_source_tokens(self):
        report = verify_pseudo_prod(self.source, self.target, self.key)
        self.assertEqual(report['non_keyed_values'], 0)
        self.assertEqual(report['orphaned_employment_links'], 0)
        self.assertGreater(sum(field['values_checked'] for field in report['fields'].values()), 0)
        self.assertIn('business.people.national_id', report['fields'])
        self.assertIn('business.people.email', report['fields'])
        self.assertIn('business.employment.employee_email', report['fields'])

    def test_a_different_key_detects_non_keyed_values(self):
        wrong_key = hashlib.sha256(self.key).digest()
        report = verify_pseudo_prod(self.source, self.target, wrong_key)
        self.assertGreater(report['non_keyed_values'], 0)

    def test_wrong_key_cannot_retokenize_existing_values(self):
        with self.assertRaises(ValueError):
            tokenize_pseudo_prod(self.source, self.target, hashlib.sha256(self.key).digest())
        self.assertEqual(verify_pseudo_prod(self.source, self.target, self.key)['non_keyed_values'], 0)

    def test_original_database_cannot_be_used_as_the_update_target(self):
        with self.assertRaises(ValueError):
            tokenize_pseudo_prod(self.source, self.source, self.key)

    def test_a_format_shaped_forgery_is_detected(self):
        with self.target.transaction(force_rollback=True):
            self.target.execute('''UPDATE business.people SET national_id=%s
                WHERE person_id=(SELECT min(person_id) FROM business.people)''',
                ('hmac_nid_' + '0' * 64,))
            report = verify_pseudo_prod(self.source, self.target, self.key)
            self.assertEqual(report['fields']['business.people.national_id']['non_keyed_values'], 1)
        self.assertEqual(verify_pseudo_prod(self.source, self.target, self.key)['non_keyed_values'], 0)

    def test_rerun_is_idempotent_and_preserves_foreign_keys(self):
        before = self.target.execute('''SELECT conname, condeferrable, condeferred, convalidated
            FROM pg_constraint WHERE conrelid='business.employment'::regclass AND contype='f'
            ORDER BY conname''').fetchall()
        report = tokenize_pseudo_prod(self.source, self.target, self.key)
        self.assertEqual(report['updated_rows'], 0)
        self.assertEqual(report['non_keyed_values'], 0)
        self.assertEqual(report['orphaned_employment_links'], 0)
        after = self.target.execute('''SELECT conname, condeferrable, condeferred, convalidated
            FROM pg_constraint WHERE conrelid='business.employment'::regclass AND contype='f'
            ORDER BY conname''').fetchall()
        self.assertEqual(before, after)
        source_constraints = self.source.execute('''SELECT conname, condeferrable, condeferred, convalidated
            FROM pg_constraint WHERE conrelid='business.employment'::regclass AND contype='f'
            ORDER BY conname''').fetchall()
        self.assertEqual(after, source_constraints)
        self.assertTrue(all(row[3] for row in after))

    def test_nullable_json_remains_sql_null(self):
        column = self.source.execute("""SELECT 1 FROM information_schema.columns
            WHERE table_schema='business' AND table_name='people' AND column_name='payload'""").fetchone()
        if column:
            source_nulls = self.source.execute('SELECT count(*) FROM business.people WHERE payload IS NULL').fetchone()[0]
            target_nulls = self.target.execute('SELECT count(*) FROM business.people WHERE payload IS NULL').fetchone()[0]
            self.assertEqual(source_nulls, target_nulls)


if __name__ == '__main__':
    unittest.main()
