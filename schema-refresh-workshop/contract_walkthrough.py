"""Live acceptance checks; resets only this workshop's synthetic source/target."""

from copy import deepcopy
from dataclasses import replace
import argparse
import json
import os
from pathlib import Path
import sys
import shutil
from tempfile import TemporaryDirectory
from types import ModuleType

import psycopg
from psycopg import sql

from contract_refresh import run
from preprod_schema import SCHEMA, TARGET_SCHEMA, VIEWER_ROLE
from refresh import ReviewRequired, apply_migration, connect, initialize, verify
from schema_contract import ForeignKey, constant
from walkthrough import published_hash


def module_for(definition):
    module = ModuleType("acceptance_definition")
    module.SCHEMA, module.TARGET_SCHEMA, module.VIEWER_ROLE = definition, TARGET_SCHEMA, VIEWER_ROLE
    sys.modules[module.__name__] = module
    return module.__name__


def main(examples=None):
    initialize(100)
    with TemporaryDirectory() as directory:
        artifacts = Path(directory)
        run(inspect_only=True, artifacts=artifacts)
        assert not (artifacts / "production.previous.json").exists()
        run(artifacts=artifacts)
        verify()
        baseline = (artifacts / "production.previous.json").read_bytes()
        assert baseline == (artifacts / "production.current.json").read_bytes()
        print("PASS: sorted snapshots exported; baseline advances only after publication")

        before = published_hash()
        apply_migration("new-columns")
        apply_migration("ambiguous")
        try:
            run(inspect_only=True, artifacts=artifacts)
        except ReviewRequired:
            assert published_hash() == before
            assert (artifacts / "production.previous.json").read_bytes() == baseline
            changes = json.loads((artifacts / "schema.diff.json").read_text())["changes"]
            assert [change["column"] for change in changes] == [
                "emergency_contact_email", "favorite_color", "internal_memo", "payload"]
        else:
            raise AssertionError("Unmapped columns were not blocked")
        print("PASS: four new columns appear alphabetically in diff; inspect cannot approve them")
        if examples:
            examples.mkdir(parents=True, exist_ok=True)
            for name in ("production.previous.json", "production.previous.txt", "production.current.json",
                         "production.current.txt", "schema.diff.json", "preprod.sql", "column-mapping.txt"):
                shutil.copyfile(artifacts / name, examples / name)

        solution = "solutions.preprod_schema_after_drift"
        run(definition_module=solution, artifacts=artifacts)
        verify()
        assert (artifacts / "production.previous.json").read_bytes() != baseline
        before = published_hash()
        previous = (artifacts / "production.previous.json").read_bytes()
        with connect("SOURCE_ADMIN_DSN") as source:
            source.execute("UPDATE business.people SET favorite_color='not-an-approved-color' WHERE person_id=1")
        try:
            run(definition_module=solution, artifacts=artifacts)
        except ValueError:
            assert published_hash() == before
            assert (artifacts / "production.previous.json").read_bytes() == previous
        else:
            raise AssertionError("Domain violation was copied")
        with connect("SOURCE_ADMIN_DSN") as source:
            source.execute("UPDATE business.people SET favorite_color='green' WHERE person_id=1")
        print("PASS: domain violation rolls back staging and preserves preprod/baseline")

        from solutions.preprod_schema_after_drift import SCHEMA as COMPLETE
        broken = deepcopy(COMPLETE)
        broken["employment"].columns["salary_eur"] = replace(broken["employment"].columns["salary_eur"], rule=constant(0))
        try:
            run(definition_module=module_for(broken), artifacts=artifacts)
        except psycopg.errors.CheckViolation:
            assert published_hash() == before
            assert (artifacts / "production.previous.json").read_bytes() == previous
        else:
            raise AssertionError("Target CHECK constraint was not enforced")
        print("PASS: code-defined target CHECK prevents invalid salary publication")

        renamed = deepcopy(COMPLETE)
        renamed["people"].columns["email_token"] = renamed["people"].columns.pop("email")
        renamed["people"] = replace(renamed["people"], unique=(("email_token",), ("national_id",)))
        renamed["employment"] = replace(renamed["employment"], foreign_keys=(
            ForeignKey(("company_id",), "companies", ("company_id",)),
            ForeignKey(("employee_email",), "people", ("email_token",)),
        ))
        run(definition_module=module_for(renamed), artifacts=artifacts)
        with connect("TARGET_DSN") as target:
            assert target.execute("SELECT count(*) FROM business.people p JOIN business.employment e ON p.email_token=e.employee_email").fetchone()[0] == 100
            assert target.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='business' AND table_name='people' AND column_name='email'").fetchone()[0] == 0
            assert target.execute("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'stage_%'").fetchone()[0] == 0
        print("PASS: renamed target column and its foreign key come from Python, not source DDL")
        run(definition_module=solution, artifacts=artifacts)
        verify()
        # Reuse must not depend on the workshop's source schema name.
        original_schema = os.environ.get("SOURCE_SCHEMA")
        try:
            with connect("SOURCE_ADMIN_DSN") as source:
                source.execute(sql.SQL("ALTER SCHEMA business RENAME TO {}").format(sql.Identifier("source fixture")))
            os.environ["SOURCE_SCHEMA"] = "source fixture"
            run(definition_module=solution, artifacts=artifacts)
            verify()
            assert json.loads((artifacts / "production.current.json").read_text())["schema"] == "source fixture"
        finally:
            with connect("SOURCE_ADMIN_DSN") as source:
                source.execute(sql.SQL("ALTER SCHEMA {} RENAME TO business").format(sql.Identifier("source fixture")))
            if original_schema is None:
                os.environ.pop("SOURCE_SCHEMA", None)
            else:
                os.environ["SOURCE_SCHEMA"] = original_schema
        print("PASS: configurable source schema works, including a quoted identifier")
        with connect("SOURCE_ADMIN_DSN") as source:
            source.execute("CREATE TABLE business.unmapped_empty_table ()")
        try:
            run(inspect_only=True, definition_module=solution, artifacts=artifacts)
        except ReviewRequired:
            document = json.loads((artifacts / "production.current.json").read_text())
            assert "unmapped_empty_table" in [table["name"] for table in document["tables"]]
        else:
            raise AssertionError("Zero-column source table was silently ignored")
        finally:
            with connect("SOURCE_ADMIN_DSN") as source:
                source.execute("DROP TABLE business.unmapped_empty_table")
        print("PASS: even a zero-column source table is captured and blocks copying")
        run(definition_module=solution, artifacts=artifacts)
    print("All code-defined cloning acceptance checks passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, help="Export metadata-only examples generated by the live databases")
    main(parser.parse_args().examples)
