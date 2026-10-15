"""Production snapshot refresh with schema drift detection and publication gates."""

import argparse
from datetime import date
import json
import os
from pathlib import Path
import secrets
import time

import psycopg
from psycopg import sql

from catalog import column_signature, constraint_signature, digest, full_domain_is_safe, inventory, validate_supported_schema
from classification import classify
from clone import publish

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get("STATE_DIR", "/state"))


class ReviewRequired(Exception):
    pass


def connect(name):
    for attempt in range(20):
        try:
            return psycopg.connect(os.environ[name], autocommit=True)
        except psycopg.OperationalError:
            if attempt == 19:
                raise
            time.sleep(1)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_policy():
    path = STATE / "policy.json"
    if not path.exists():
        raise ReviewRequired("Initialize the synthetic workshop first")
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_policy(tables, actions):
    return {"columns": {f"{table_name}.{column['column_name']}": {
                "signature": column_signature(column), "rule": actions[f"{table_name}.{column['column_name']}"]}
                for table_name, table in tables.items() for column in table["columns"]},
            "constraints": {table_name: constraint_signature(table) for table_name, table in tables.items()}}


def lock_source(source, tables):
    for table_name in sorted(tables):
        source.execute(sql.SQL("LOCK TABLE {} IN ACCESS SHARE MODE").format(sql.Identifier("business", table_name)))


def initialize(people=1000):
    if people < 2:
        raise ValueError("Use at least two synthetic people")
    with connect("SOURCE_ADMIN_DSN") as source:
        with source.transaction():
            source.execute((ROOT / "schema.sql").read_text())
            with source.cursor() as cursor:
                cursor.executemany("INSERT INTO business.companies VALUES (%s,%s,%s)",
                                   [(i, f"Demo Company {i}", i * 98765) for i in range(1, 11)])
                cursor.executemany("INSERT INTO business.people VALUES (%s,%s,%s,%s,%s,%s)",
                                   [(i, "Ąžuolas" if i % 2 else "Ūla", "Žukauskas" if i % 2 else "Šimkutė",
                                     f"person-{i}@example.com", f"390{i:08d}", date(1990 + i % 20, 1, 1))
                                    for i in range(1, people + 1)])
                cursor.executemany("INSERT INTO business.employment VALUES (%s,%s,%s,%s,%s)",
                                   [(i, f"person-{i}@example.com", 1 + i % 10, 2000 + i % 4000,
                                     "Engineering" if i % 2 else "Sales") for i in range(1, people + 1)])
    with connect("TARGET_DSN") as target:
        with target.transaction():
            target.execute("DROP SCHEMA IF EXISTS business CASCADE; DROP SCHEMA IF EXISTS legacy CASCADE")
            target.execute("""DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'preprod_viewer') THEN
                    CREATE ROLE preprod_viewer LOGIN PASSWORD 'viewer-demo';
                END IF;
            END $$""")
    with connect("SOURCE_DSN") as source:
        tables = inventory(source)
    actions = json.loads((ROOT / "baseline_actions.json").read_text())
    write_json(STATE / "policy.json", snapshot_policy(tables, actions))
    STATE.mkdir(parents=True, exist_ok=True)
    key_path = STATE / "pseudonym.key"
    if not key_path.exists():
        key_path.write_bytes(secrets.token_bytes(32))
        key_path.chmod(0o600)
    print(f"Initialized synthetic production: {people} people, {people} contracts, 10 companies")


def apply_migration(name):
    filenames = {"new-columns": "new_columns.sql", "ambiguous": "ambiguous_column.sql"}
    with connect("SOURCE_ADMIN_DSN") as source:
        with source.transaction():
            source.execute((ROOT / "migrations" / filenames[name]).read_text())
    print(f"Applied synthetic production migration: {name}")


def analyze(source, tables, policy):
    decisions = []
    blockers = []
    actions = {}
    current = set()
    for table_name, table in tables.items():
        if policy["constraints"].get(table_name) != constraint_signature(table):
            blockers.append(f"{table_name}: new table or changed constraints require review")
        for column in table["columns"]:
            key = f"{table_name}.{column['column_name']}"
            current.add(key)
            existing = policy["columns"].get(key)
            if existing:
                if existing["signature"] != column_signature(column):
                    blockers.append(f"{key}: changed column definition requires review")
                else:
                    actions[key] = existing["rule"]
                    if "domain" in existing["rule"] and not full_domain_is_safe(source, table_name, column, existing["rule"]["domain"]):
                        blockers.append(f"{key}: values escaped the approved benign domain")
            else:
                decision = classify(source, table_name, column)
                decisions.append(decision)
                if decision["decision"] == "review":
                    blockers.append(f"{key}: classification requires review")
                else:
                    actions[key] = decision["rule"]
    for removed in set(policy["columns"]) - current:
        blockers.append(f"{removed}: column disappeared")
    report = {"schema_hash": digest({name: [column_signature(c) for c in table["columns"]]
                                     for name, table in tables.items()}),
              "decisions": decisions, "blockers": blockers, "can_publish": not blockers}
    write_json(STATE / "last_report.json", report)
    return report, actions


def run_refresh(mode="guarded", scan_only=False):
    policy = load_policy()
    with connect("SOURCE_DSN") as source:
        with source.transaction():
            source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            tables = inventory(source)
            lock_source(source, tables)
            validate_supported_schema(tables)
            if mode == "legacy":
                baseline = json.loads((ROOT / "baseline_actions.json").read_text())
                actions = {f"{name}.{column['column_name']}": baseline.get(
                    f"{name}.{column['column_name']}", {"action": "keep"})
                    for name, table in tables.items() for column in table["columns"]}
                report = {"mode": "legacy", "warning": "Unrecognized columns are copied unchanged into the legacy schema"}
            else:
                report, actions = analyze(source, tables, policy)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            if mode != "legacy" and report["blockers"]:
                raise ReviewRequired("Refresh blocked; the published preprod schema is unchanged")
            if scan_only:
                return report
            with connect("TARGET_DSN") as target:
                acquired = target.execute("SELECT pg_try_advisory_lock(784321)").fetchone()[0]
                if not acquired:
                    raise ReviewRequired("Another refresh holds the publication lock")
                with target.transaction():
                    counts = publish(source, target, tables, actions, (STATE / "pseudonym.key").read_bytes(),
                                     destination="legacy" if mode == "legacy" else "business")
                    if mode != "legacy":
                        write_json(STATE / "policy.json", snapshot_policy(tables, actions))
            print(json.dumps({"published": "legacy" if mode == "legacy" else "business", "rows": counts}))
            return counts


def approve(key, action):
    policy = load_policy()
    with connect("SOURCE_DSN") as source:
        tables = inventory(source)
    columns = {f"{name}.{column['column_name']}": column for name, table in tables.items() for column in table["columns"]}
    if key not in columns:
        raise ValueError("Column does not exist")
    if action == "null" and not columns[key]["nullable"]:
        raise ValueError("Cannot null a NOT NULL column")
    policy["columns"][key] = {"signature": column_signature(columns[key]), "rule": {"action": action}}
    write_json(STATE / "policy.json", policy)
    print(f"Reviewed column {key}: {action}; publication still requires validation")


def verify(legacy=False):
    schema = "legacy" if legacy else "business"
    with connect("TARGET_DSN") as target:
        people = target.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(schema, "people"))).fetchone()[0]
        joins = target.execute(sql.SQL("SELECT count(*) FROM {} e JOIN {} p ON p.email=e.employee_email").format(
            sql.Identifier(schema, "employment"), sql.Identifier(schema, "people"))).fetchone()[0]
        assert people == joins, "PII-based email relationships were broken"
        assert target.execute(sql.SQL("SELECT count(*) FROM {} WHERE email LIKE '%%@example.com'").format(
            sql.Identifier(schema, "people"))).fetchone()[0] == 0, "Original person emails survived"
        assert target.execute(sql.SQL("SELECT count(*) FROM {} WHERE national_id !~ '^id-[0-9a-f]{{32}}$'").format(
            sql.Identifier(schema, "people"))).fetchone()[0] == 0, "Personal codes were not pseudonymized"
        baseline = json.loads((ROOT / "baseline_actions.json").read_text())
        for key, rule in baseline.items():
            if rule["action"] == "constant":
                table_name, column = key.split(".")
                value = date.fromisoformat(rule["value"]) if column == "birth_date" else rule["value"]
                count = target.execute(sql.SQL("SELECT count(*) FROM {} WHERE {} IS DISTINCT FROM %s").format(
                    sql.Identifier(schema, table_name), sql.Identifier(column)), (value,)).fetchone()[0]
                assert count == 0, f"Known sensitive field was not transformed: {key}"
        for column in ("emergency_contact_email", "payload", "internal_memo"):
            exists = target.execute("SELECT EXISTS(SELECT FROM information_schema.columns WHERE table_schema=%s AND table_name='people' AND column_name=%s)",
                                    (schema, column)).fetchone()[0]
            if exists:
                leaked = target.execute(sql.SQL("SELECT count(*) FROM {} WHERE {} IS NOT NULL").format(
                    sql.Identifier(schema, "people"), sql.Identifier(column))).fetchone()[0]
                assert leaked == 0, f"Sensitive data survived in {column}: {leaked} rows"
    print(f"PASS: {people} people; email-based joins preserved; drifted sensitive fields removed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--people", type=int, default=1000)
    migration = commands.add_parser("migrate")
    migration.add_argument("name", choices=["new-columns", "ambiguous"])
    commands.add_parser("scan")
    refresh = commands.add_parser("refresh")
    refresh.add_argument("--mode", choices=["guarded", "legacy"], default="guarded")
    review = commands.add_parser("approve")
    review.add_argument("column")
    review.add_argument("--action", choices=["null", "keep"], required=True)
    check = commands.add_parser("verify")
    check.add_argument("--legacy", action="store_true")
    watch = commands.add_parser("watch")
    watch.add_argument("--interval", type=float, default=30)
    commands.add_parser("report")
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize(args.people)
        elif args.command == "migrate":
            apply_migration(args.name)
        elif args.command in {"scan", "refresh"}:
            run_refresh(getattr(args, "mode", "guarded"), scan_only=args.command == "scan")
        elif args.command == "approve":
            approve(args.column, args.action)
        elif args.command == "verify":
            verify(args.legacy)
        elif args.command == "report":
            print((STATE / "last_report.json").read_text())
        elif args.command == "watch":
            if args.interval < 5:
                raise ValueError("Interval must be at least five seconds")
            while True:
                try:
                    run_refresh()
                except (ReviewRequired, psycopg.Error, ValueError) as error:
                    print(json.dumps({"refresh": "blocked", "error_type": type(error).__name__}))
                time.sleep(args.interval)
        return 0
    except ReviewRequired as error:
        print(str(error))
        return 2
    except (psycopg.Error, ValueError) as error:
        # PostgreSQL exception detail may contain raw values; never print it.
        print(json.dumps({"refresh": "failed", "error_type": type(error).__name__, "published_preprod": "unchanged"}))
        return 1
    except AssertionError as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
