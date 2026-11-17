"""Exercise the complete refresh against disposable databases, never the lab copies."""

import os
from pathlib import Path
import secrets
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mask_pseudo_prod import verify_masking
from refresh_pseudo_prod import SchemaMismatch, database_dsn, refresh
from tokenize_pseudo_prod import verify_pseudo_prod


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.key = secrets.token_bytes(32)
        self.key_file = self.directory / 'key'
        self.key_file.write_bytes(self.key)
        self.source_name = 'refresh_test_source_' + uuid.uuid4().hex
        self.target_name = 'refresh_test_target_' + uuid.uuid4().hex
        dsn = os.environ['PSEUDO_PROD_DSN']
        self.admin = psycopg.connect(database_dsn(dsn, 'postgres'), autocommit=True)
        self.addCleanup(self.admin.close)
        schema = (Path(__file__).resolve().parents[1] / 'schema.sql').read_text().split('DO $$')[0]
        for name in (self.source_name, self.target_name):
            self.admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
            self.addCleanup(self.drop_database, name)
            with psycopg.connect(database_dsn(dsn, name), autocommit=True) as connection:
                connection.execute(schema)
                connection.execute('''INSERT INTO business.companies VALUES (1, 'Fixture company', 12);
                    INSERT INTO business.people VALUES
                      (1, 'Fixture', 'One', 'one@example.invalid', 'fixture-id-one', '1990-01-01'),
                      (2, 'Fixture', 'Two', 'two@example.invalid', 'fixture-id-two', '1991-01-01');
                    INSERT INTO business.employment VALUES
                      (1, 'one@example.invalid', 1, 100, 'Test'),
                      (2, 'two@example.invalid', 1, 200, 'Test')''')
        self.source_dsn = database_dsn(dsn, self.source_name)
        self.target_dsn = database_dsn(dsn, self.target_name)

    def drop_database(self, name):
        self.admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))

    def run_refresh(self):
        return refresh(self.source_dsn, self.target_dsn, self.key_file, self.directory / 'artifacts',
                       expected_database=self.target_name)

    def fingerprint(self, dsn):
        with psycopg.connect(dsn, autocommit=True) as connection:
            return [connection.execute(sql.SQL('SELECT md5(string_agg(row_to_json(t)::text,\n'
                "'' ORDER BY row_to_json(t)::text)) FROM business.{} t").format(sql.Identifier(table))).fetchone()[0]
                for table in ('people', 'companies', 'employment')]

    def staging_databases(self):
        return self.admin.execute("SELECT datname FROM pg_database WHERE datname LIKE 'pseudo_stage_%' ORDER BY datname").fetchall()

    def test_mismatch_blocks_before_cloning_and_preserves_target(self):
        before = self.fingerprint(self.target_dsn)
        with psycopg.connect(self.source_dsn, autocommit=True) as source:
            source.execute('ALTER TABLE business.people ADD COLUMN address text')
        with patch('refresh_pseudo_prod.postgres_tool') as dump:
            with self.assertRaises(SchemaMismatch):
                self.run_refresh()
            dump.assert_not_called()
        self.assertEqual(before, self.fingerprint(self.target_dsn))
        self.assertIn('+  address: text', (self.directory / 'artifacts/schema.diff').read_text())

    def test_matching_schemas_clone_mask_and_support_repeated_refresh(self):
        # A new source row must appear in the clone, rather than just masking old data.
        with psycopg.connect(self.source_dsn, autocommit=True) as source:
            source.execute("""INSERT INTO business.people VALUES
                (3, 'New', 'Fixture', 'three@example.invalid', 'fixture-id-three', '1992-01-01');
                INSERT INTO business.employment VALUES (3, 'three@example.invalid', 1, 300, 'Test')""")
        before = self.fingerprint(self.source_dsn)
        for _ in range(2):
            report = self.run_refresh()
            self.assertEqual(report['status'], 'refreshed')
            self.assertEqual(report['row_counts']['business.people'], 3)
            self.assertEqual(report['non_keyed_values'], 0)
            self.assertEqual(report['unmasked_values'], 0)
            with psycopg.connect(self.source_dsn, autocommit=True) as source, \
                 psycopg.connect(self.target_dsn, autocommit=True) as target:
                self.assertEqual(verify_pseudo_prod(source, target, self.key,
                    expected_database=self.target_name)['non_keyed_values'], 0)
                self.assertEqual(verify_masking(target,
                    expected_database=self.target_name)['total_unmasked_values'], 0)
            self.assertEqual(before, self.fingerprint(self.source_dsn))

    def test_anonymisation_failure_preserves_old_target_and_removes_raw_stage(self):
        before = self.fingerprint(self.target_dsn)
        stages = self.staging_databases()
        with patch('refresh_pseudo_prod.mask_pseudo_prod', side_effect=ValueError('simulated failure')):
            with self.assertRaises(ValueError):
                self.run_refresh()
        self.assertEqual(before, self.fingerprint(self.target_dsn))
        self.assertEqual(stages, self.staging_databases())

    def test_active_target_client_blocks_publication_without_data_loss(self):
        before = self.fingerprint(self.target_dsn)
        stages = self.staging_databases()
        with psycopg.connect(self.target_dsn, autocommit=True):
            with self.assertRaises(psycopg.errors.ObjectInUse):
                self.run_refresh()
        self.assertEqual(before, self.fingerprint(self.target_dsn))
        self.assertEqual(stages, self.staging_databases())

    def test_missing_key_blocks_without_replacing_target(self):
        before = self.fingerprint(self.target_dsn)
        self.key_file.unlink()
        with self.assertRaises(FileNotFoundError):
            self.run_refresh()
        self.assertEqual(before, self.fingerprint(self.target_dsn))

    def test_default_target_guard_rejects_any_other_database(self):
        with self.assertRaises(ValueError):
            refresh(self.source_dsn, self.target_dsn, self.key_file, self.directory / 'artifacts')


if __name__ == '__main__':
    unittest.main()
