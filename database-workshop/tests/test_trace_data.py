"""Unit tests plus opt-in PostgreSQL integration tests in a disposable database."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trace_data", ROOT / "trace_data.py")
trace_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace_data)


class ReportTests(unittest.TestCase):
    def test_database_values_are_escaped_in_html(self):
        rendered = trace_data.row_table([{"email": '<script>alert("x")</script>'}])
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_comparison_rejects_changed_public_record(self):
        before = {"format_version": 1, "seed": {"directory_id": 42, "postcode": "ABC"}}
        after = {"format_version": 1, "seed": {"directory_id": 42, "postcode": "XYZ"}}
        with self.assertRaisesRegex(ValueError, "unchanged public"):
            trace_data.validate_pair(before, after)

    def test_report_files_are_private(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            trace_data.write_reports(target, "trace.json", "trace.html", {}, "<html></html>")
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            self.assertEqual((target / "trace.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual((target / "trace.html").stat().st_mode & 0o777, 0o600)


FIXTURE = """
INSERT INTO private_db.company VALUES
(1,'CR1','Example Company','IT','Vilnius',3,100000,9000);
INSERT INTO private_db.person_identity VALUES
(42,'N42','T42','Ada','Example','1990-01-01','ada@example.test','+3700042','Street','Vilnius','LT001'),
(43,'N43','T43','Bea','Example','1990-01-01','bea@example.test','+3700043','Street','Vilnius','LT001');
INSERT INTO private_db.employment_contract VALUES
(42,'N42','ada@example.test','CR1','Engineer','IT','2020-01-01',4000,100,NULL),
(43,'N43','bea@example.test','CR1','Engineer','IT','2020-01-01',5000,100,NULL);
INSERT INTO private_db.payroll_event VALUES
(1,'ada@example.test','2026-01-01',4000,1000,'BANK42'),
(2,'ada@example.test','2026-02-01',4000,1000,'BANK42');
INSERT INTO private_db.benefit_claim VALUES
(1,'+3700042','2026-01-01','Synthetic condition','Vilnius',100,true);
INSERT INTO private_db.application_user VALUES (42,'ada@example.test','employee',false,false);
INSERT INTO public_db.people_directory VALUES
(42,'Ada','Example','1990-01-01','Vilnius','LT001','https://example.test/42');
INSERT INTO public_db.professional_profile VALUES
(42,'Ada','Example','Vilnius','LT001','Example Company','Engineer','Senior','3000-5000','https://example.test/42');
INSERT INTO public_db.company_registry VALUES
(1,'CR1','Example Company','IT','Vilnius','1-10','100k','positive');
INSERT INTO public_db.procurement_award VALUES (1,'CR1','2026-01-01','Buyer','IT',500);
CREATE SCHEMA masked_private;
"""


@unittest.skipUnless(os.environ.get("WORKSHOP_TRACE_INTEGRATION") == "1", "Set WORKSHOP_TRACE_INTEGRATION=1 for isolated PostgreSQL tests")
class PostgresTests(unittest.TestCase):
    @classmethod
    def psql(cls, database, sql):
        result = subprocess.run([
            "docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "exec", "-T", "postgres",
            "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-U", "workshop", "-d", database,
        ], input=sql, text=True, capture_output=True, timeout=90)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return result.stdout

    @classmethod
    def setUpClass(cls):
        # The name is generated locally; the existing workshop database is never reset.
        cls.database = "trace_test_" + uuid.uuid4().hex
        cls.psql("postgres", f'CREATE DATABASE "{cls.database}";')
        cls.addClassCleanup(cls.psql, "postgres", f'DROP DATABASE "{cls.database}";')
        cls.psql(cls.database, (ROOT / "schema.sql").read_text() + FIXTURE)
        for scope, table, *_ in trace_data.TABLES:
            if scope == "private":
                cls.psql(cls.database, f"CREATE TABLE masked_private.{table} (LIKE private_db.{table} INCLUDING ALL); INSERT INTO masked_private.{table} SELECT * FROM private_db.{table};")
        cls.psql(cls.database, "UPDATE masked_private.person_identity SET first_name='Person', last_name='Anonymous';")

    def run_trace(self, schema="private_db", person=42):
        with tempfile.TemporaryDirectory() as output:
            result = subprocess.run([
                "python3", str(ROOT / "trace_data.py"), "trace", "--database", self.database,
                "--private-schema", schema, "--person", str(person), "--limit", "1", "--output-dir", output,
            ], text=True, capture_output=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads((Path(output) / "trace.json").read_text())

    def test_detects_ambiguity_and_counts_beyond_sample_limit(self):
        report = self.run_trace()
        methods = {m["path"]: m for m in report["methods"]}
        self.assertEqual(methods["name_birth_postcode"]["candidate_count"], 1)
        self.assertEqual(methods["birth_postcode_job"]["candidate_count"], 2)
        self.assertEqual(len(methods["birth_postcode_job"]["candidate_ids"]), 1)
        tables = {t["name"]: t for t in report["tables"]}
        self.assertEqual(tables["payroll_event"]["count"], 2)
        self.assertEqual(len(tables["payroll_event"]["rows"]), 1)
        self.assertEqual(tables["benefit_claim"]["count"], 1)
        self.assertEqual(tables["company"]["rows"][0]["annual_profit_eur"], 9000)

    def test_masking_names_keeps_other_linkage_paths(self):
        before, after = self.run_trace(), self.run_trace("masked_private")
        methods = {m["path"]: m["candidate_count"] for m in after["methods"]}
        self.assertEqual(methods["name_birth_postcode"], 0)
        self.assertEqual(methods["birth_postcode_job"], 2)
        self.assertEqual(methods["preserved_person_id"], 1)
        self.assertEqual(methods["preserved_contract_id"], 1)
        self.assertIn("Before / after linkage comparison", trace_data.render_comparison(before, after))

    def test_query_transaction_prevents_writes(self):
        sql = trace_data.build_sql().split("WITH\n", 1)[0]
        sql += "DELETE FROM private_db.person_identity;"
        # Executing a write inside the same read-only transaction must fail.
        with self.assertRaisesRegex(RuntimeError, "read-only transaction"):
            self.psql(self.database, sql)


if __name__ == "__main__":
    unittest.main()
