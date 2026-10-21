"""Export sorted production schemas, compare files, and publish a code-defined clone."""

import argparse
import importlib
import json
import os
from pathlib import Path

import psycopg
from psycopg import sql

from catalog import inventory, validate_supported_schema
from refresh import STATE, ReviewRequired, connect
from schema_contract import ddl, mapping_text, publish, validate
from schema_files import atomic_text, compare, snapshot, write_json, write_snapshot


def run(*, inspect_only=False, definition_module="preprod_schema", artifacts=None):
    module = importlib.import_module(definition_module)
    definition = module.SCHEMA
    directory = Path(artifacts or os.environ.get("ARTIFACT_DIR", "/artifacts"))
    source_schema = os.environ.get("SOURCE_SCHEMA", "business")
    previous_path = directory / "production.previous.json"
    # The source snapshot covers both introspection and row reads.
    with connect("SOURCE_DSN") as source:
        with source.transaction():
            source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            tables = inventory(source, source_schema)
            for name in sorted(tables):
                source.execute(sql.SQL("LOCK TABLE {} IN ACCESS SHARE MODE").format(sql.Identifier(source_schema, name)))
            current = snapshot(tables, source_schema)
            write_snapshot(directory / "production.current.json", current)
            previous = json.loads(previous_path.read_text()) if previous_path.exists() else None
            difference = compare(previous, current)
            write_json(directory / "schema.diff.json", difference)
            problems = validate(tables, definition)
            try:
                validate_supported_schema(tables, source_schema)
            except ValueError as error:
                problems.append(str(error))
            # Code defines the target even when new source fields block copying.
            atomic_text(directory / "column-mapping.txt", mapping_text(definition))
            atomic_text(directory / "preprod.sql", ddl(module.TARGET_SCHEMA, definition))
            report = {"can_publish": not problems, "blockers": problems, "schema_diff": difference,
                      "definition": definition_module, "target_schema": module.TARGET_SCHEMA}
            write_json(directory / "refresh.plan.json", report)
            print(json.dumps(report, indent=2, sort_keys=True))
            if problems:
                raise ReviewRequired("Copy blocked. Review schema.diff.json and update preprod_schema.py.")
            if inspect_only:
                return report
            key_path = STATE / "pseudonym.key"
            if not key_path.exists():
                raise ReviewRequired("Initialize the workshop first; no pseudonym key exists.")
            with connect("TARGET_DSN") as target:
                if not target.execute("SELECT pg_try_advisory_lock(784321)").fetchone()[0]:
                    raise ReviewRequired("Another refresh holds the publication lock")
                # A failed transform, domain check, FK or CHECK rolls back publication.
                counts = publish(source, target, tables, definition, key_path.read_bytes(),
                                 source_schema=source_schema, target_schema=module.TARGET_SCHEMA,
                                 viewer=module.VIEWER_ROLE)
                # Baseline advances only after a successful target transaction.
                write_snapshot(previous_path, current)
            print(json.dumps({"published": module.TARGET_SCHEMA, "rows": counts}, sort_keys=True))
            return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect", "refresh"])
    parser.add_argument("--definition", default="preprod_schema", help="Python module containing SCHEMA, TARGET_SCHEMA and VIEWER_ROLE")
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    try:
        run(inspect_only=args.command == "inspect", definition_module=args.definition, artifacts=args.artifacts)
        return 0
    except ReviewRequired as error:
        print(str(error))
        return 2
    except (psycopg.Error, ValueError, OSError) as error:
        # Database exception details can contain source values; print only the class.
        print(json.dumps({"refresh": "failed", "error_type": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
