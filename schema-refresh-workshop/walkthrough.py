"""Reset this synthetic workshop and verify its full drift-detection sequence."""

import copy
import psycopg
from psycopg import sql

from catalog import inventory
from clone import publish
from refresh import (STATE, ReviewRequired, approve, apply_migration, connect,
                     initialize, load_policy, run_refresh, verify)


def published_hash():
    with connect("TARGET_DSN") as target:
        results = []
        for table, key in (("people", "person_id"), ("employment", "contract_id"), ("companies", "company_id")):
            query = sql.SQL("SELECT md5(string_agg(to_jsonb(t)::text, ',' ORDER BY {})) FROM {} t").format(
                sql.Identifier(key), sql.Identifier("business", table))
            results.append(target.execute(query).fetchone()[0])
        return results


def main():
    initialize()
    run_refresh()
    verify()
    print("PASS: baseline refresh anonymizes known fields and preserves email joins")

    apply_migration("new-columns")
    run_refresh("legacy")
    try:
        verify(legacy=True)
    except AssertionError:
        print("PASS: reproduced legacy-policy leakage from newly added columns")
    else:
        raise AssertionError("Legacy example did not reproduce leakage")
    report = run_refresh(scan_only=True)
    decisions = {row["column"]: row["decision"] for row in report["decisions"]}
    assert decisions == {"people.emergency_contact_email": "anonymize", "people.payload": "anonymize", "people.favorite_color": "keep"}
    run_refresh()
    verify()
    print("PASS: named email and sparse nested JSON were nulled; benign colors retained")

    before = published_hash()
    with connect("SOURCE_ADMIN_DSN") as source:
        source.execute("UPDATE business.people SET favorite_color='out-of-domain' WHERE person_id=1")
    try:
        run_refresh()
    except ReviewRequired:
        assert published_hash() == before
        print("PASS: previously approved domain drift blocked publication")
    else:
        raise AssertionError("Domain drift was not blocked")
    with connect("SOURCE_ADMIN_DSN") as source:
        source.execute("UPDATE business.people SET favorite_color='green' WHERE person_id=1")

    apply_migration("ambiguous")
    try:
        run_refresh()
    except ReviewRequired:
        assert published_hash() == before
        print("PASS: ambiguous new column blocked publication without changing preprod")
    else:
        raise AssertionError("Ambiguous field was silently approved")
    approve("people.internal_memo", "null")
    run_refresh()
    verify()

    actions = {key: value["rule"] for key, value in load_policy()["columns"].items()}
    broken = copy.deepcopy(actions)
    broken["employment.salary_eur"] = {"action": "constant", "value": 0}
    before = published_hash()
    with connect("SOURCE_DSN") as source:
        with source.transaction():
            source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            tables = inventory(source)
            with connect("TARGET_DSN") as target:
                try:
                    publish(source, target, tables, broken, (STATE / "pseudonym.key").read_bytes())
                except psycopg.errors.CheckViolation:
                    assert published_hash() == before
                    assert target.execute("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'stage_%'").fetchone()[0] == 0
                    print("PASS: incompatible anonymization rolled back staging and preserved published preprod")
                else:
                    raise AssertionError("Invalid salary passed the schema CHECK constraint")
    with connect("TARGET_DSN") as target:
        assert not target.execute("SELECT has_schema_privilege('preprod_viewer','legacy','USAGE')").fetchone()[0]
    print("PASS: preprod viewer cannot access the intentionally unsafe legacy schema")
    print("All live schema-refresh workshop checks passed")


if __name__ == "__main__":
    main()
