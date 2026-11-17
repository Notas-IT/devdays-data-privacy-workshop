"""Verify that the salary-view login cannot read individual salaries."""

import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DirectSalaryRecordsTest(unittest.TestCase):
    def query(self, sql):
        project = os.environ.get(
            'WORKSHOP_COMPOSE_PROJECT', 'devdays-database-student-workshop'
        )
        return subprocess.run(
            ['docker', 'compose', '-p', project, '-f', str(ROOT / 'docker-compose.yml'),
             'exec', '-T', '-e', 'PGPASSWORD=salary-viewer-demo', 'postgres',
             'psql', '-X', '-q', '-A', '-t', '-h', '127.0.0.1',
             '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose',
             '-U', 'salary_viewer', '-d', 'privacy_workshop',
             '-c', f'BEGIN READ ONLY;\n{sql}\nROLLBACK;'],
            capture_output=True, text=True, timeout=30,
        )

    def test_connects_as_restricted_login(self):
        result = self.query('SELECT current_user;')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'salary_viewer')

    def test_direct_salary_records_are_denied(self):
        for setting in ('', "SET LOCAL app.company_id = '1';"):
            with self.subTest(company_setting=setting or 'unset'):
                result = self.query(setting + """
                    SELECT contract_id, salary_eur
                    FROM private_db.employment_contract
                    WHERE company_registration_number = 'CR00000001';
                """)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('42501', result.stderr)  # insufficient_privilege
                self.assertIn('permission denied for table employment_contract', result.stderr)
                self.assertEqual(result.stdout.strip(), '')

    def test_company_average_view_is_readable(self):
        result = self.query("""
            SET LOCAL app.company_id = '1';
            SELECT row_to_json(summary)
            FROM private_db.company_average_salary AS summary;
        """)
        self.assertEqual(result.returncode, 0, result.stderr)
        records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['company_id'], 1)
        self.assertEqual(records[0]['company_name'], 'Daukantas Energy UAB')
        self.assertEqual(set(records[0]), {'company_id', 'company_name', 'average_salary_eur'})
        self.assertGreater(records[0]['average_salary_eur'], 0)

    def test_direct_company_table_access_is_denied(self):
        result = self.query("""
            SET LOCAL app.company_id = '1';
            SELECT company_id, company_name FROM private_db.company
            WHERE company_id = 1;
        """)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('42501', result.stderr)
        self.assertIn('permission denied for table company', result.stderr)
        self.assertEqual(result.stdout.strip(), '')

    def test_view_owner_role_cannot_be_assumed(self):
        result = self.query('SET LOCAL ROLE salary_summary_owner;')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('42501', result.stderr)
        self.assertIn('salary_summary_owner', result.stderr)

    def test_view_returns_no_rows_without_company_setting(self):
        result = self.query('SELECT * FROM private_db.company_average_salary;')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '')

    def test_setting_company_session_returns_data_and_reset_hides_it(self):
        result = self.query("""
            SELECT json_build_object('phase', 'before', 'rows',
                (SELECT json_agg(summary) FROM private_db.company_average_salary AS summary));

            SET LOCAL app.company_id = '1';
            SELECT json_build_object('phase', 'selected',
                'company_setting', current_setting('app.company_id'), 'rows',
                (SELECT json_agg(summary) FROM private_db.company_average_salary AS summary));

            RESET app.company_id;
            SELECT json_build_object('phase', 'reset', 'rows',
                (SELECT json_agg(summary) FROM private_db.company_average_salary AS summary));
        """)
        self.assertEqual(result.returncode, 0, result.stderr)
        results = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0], {'phase': 'before', 'rows': None})
        self.assertEqual(results[1]['phase'], 'selected')
        self.assertEqual(results[1]['company_setting'], '1')
        self.assertEqual(len(results[1]['rows']), 1)
        company = results[1]['rows'][0]
        self.assertEqual(company['company_id'], 1)
        self.assertEqual(company['company_name'], 'Daukantas Energy UAB')
        self.assertGreater(company['average_salary_eur'], 0)
        self.assertEqual(results[2], {'phase': 'reset', 'rows': None})


if __name__ == '__main__':
    unittest.main()
