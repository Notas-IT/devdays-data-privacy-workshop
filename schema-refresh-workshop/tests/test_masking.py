"""Check the live masked clone and preservation of HMAC identifiers."""

import os
from pathlib import Path
import sys
import unittest

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mask_pseudo_prod import mask_pseudo_prod, verify_masking
from tokenize_pseudo_prod import load_key, verify_pseudo_prod


class MaskingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = psycopg.connect(os.environ['SOURCE_DSN'], autocommit=True)
        cls.target = psycopg.connect(os.environ['PSEUDO_PROD_DSN'], autocommit=True)

    @classmethod
    def tearDownClass(cls):
        cls.source.close()
        cls.target.close()

    def test_all_requested_values_are_replaced_and_rows_are_preserved(self):
        report = verify_masking(self.target)
        self.assertEqual(report['total_unmasked_values'], 0)
        for table, count in report['checked_rows'].items():
            # Table names come only from the fixed report above.
            source_count = self.source.execute(f'SELECT count(*) FROM business.{table}').fetchone()[0]
            self.assertGreater(count, 0)
            self.assertEqual(count, source_count)
        self.assertEqual(report['orphaned_employment_email_links'], 0)
        self.assertEqual(report['orphaned_company_links'], 0)

    def test_hmac_identifiers_are_preserved(self):
        report = verify_pseudo_prod(self.source, self.target, load_key())
        self.assertEqual(report['non_keyed_values'], 0)
        self.assertEqual(report['orphaned_employment_links'], 0)

    def test_rerun_makes_no_further_updates(self):
        report = mask_pseudo_prod(self.target)
        self.assertEqual(report['updated_rows'], {'people': 0, 'companies': 0, 'employment': 0})

    def test_original_database_is_rejected_as_the_update_target(self):
        with self.assertRaises(ValueError):
            mask_pseudo_prod(self.source)

    def test_verifier_detects_an_unmasked_salary(self):
        with self.target.transaction(force_rollback=True):
            self.target.execute('''UPDATE business.employment SET salary_eur=3501
                WHERE contract_id=(SELECT min(contract_id) FROM business.employment)''')
            self.assertEqual(verify_masking(self.target)['unmasked_values']['salary_eur'], 1)
        self.assertEqual(verify_masking(self.target)['total_unmasked_values'], 0)


if __name__ == '__main__':
    unittest.main()
