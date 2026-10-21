from copy import deepcopy
from dataclasses import replace

from preprod_schema import SCHEMA
from schema_contract import Column, ForeignKey, Table, ddl, keep, null, token_email, validate
from schema_files import compare, snapshot, text_schema, write_snapshot


def source_tables():
    return {table.source: {"columns": [
        {"table_name": table.source, "column_name": column.source, "type": column.pg_type,
         "nullable": column.nullable, "default_hash": None, "identity": "", "generated": ""}
        for column in table.columns.values()], "constraints": []} for table in SCHEMA.values()}


def test_snapshots_are_stable_when_catalog_order_changes(tmp_path):
    tables = source_tables()
    first = snapshot(tables)
    reordered = {name: {"columns": list(reversed(table["columns"])), "constraints": []}
                 for name, table in reversed(list(tables.items()))}
    assert snapshot(reordered) == first
    write_snapshot(tmp_path / "a.json", first)
    write_snapshot(tmp_path / "b.json", snapshot(reordered))
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    assert text_schema(first).index("companies") < text_schema(first).index("employment") < text_schema(first).index("people")
    assert [c["column_name"] for c in first["tables"][-1]["columns"]] == sorted(SCHEMA["people"].columns)


def test_snapshot_fingerprints_constraint_literals_instead_of_exporting_them():
    tables = source_tables()
    tables["people"]["constraints"] = [{"name": "check", "definition": "CHECK (email <> 'secret@example.com')", "kind": "c"}]
    result = snapshot(tables)
    assert "secret@example.com" not in str(result)
    tables["people"]["constraints"][0]["definition"] = "CHECK (email <> 'other@example.com')"
    assert compare(result, snapshot(tables))["changes"][0]["kind"] == "constraints_changed"


def test_diff_includes_added_removed_and_changed_columns_and_types():
    tables = source_tables()
    before = snapshot(tables)
    tables["people"]["columns"] = [c for c in tables["people"]["columns"] if c["column_name"] != "first_name"]
    tables["people"]["columns"][0]["type"] = "text"
    tables["people"]["columns"].append({"column_name": "new_email", "type": "text", "nullable": True})
    changes = compare(before, snapshot(tables))["changes"]
    assert [c["kind"] for c in changes] == ["column_changed", "column_removed", "column_added"]
    assert changes[0]["before"]["type"] == "date" and changes[0]["after"]["type"] == "text"


def test_diff_tracks_table_addition_removal_and_nullability():
    tables = source_tables()
    before = snapshot(tables)
    del tables["companies"]
    tables["new_table"] = {"columns": [], "constraints": []}
    tables["people"]["columns"][0]["nullable"] = True
    assert [c["kind"] for c in compare(before, snapshot(tables))["changes"]] == [
        "table_removed", "table_added", "column_changed"]
    assert compare(None, before)["baseline"]
    assert not compare(before, before)["changed"]


def test_every_source_column_needs_an_explicit_rule_or_reasoned_omission():
    tables = source_tables()
    assert validate(tables, SCHEMA) == []
    tables["people"]["columns"].append({"column_name": "payload", "type": "jsonb", "nullable": True})
    assert any("people.payload: no column rule" in p for p in validate(tables, SCHEMA))
    definition = deepcopy(SCHEMA)
    definition["people"] = replace(definition["people"], omit={"payload": "Nested data is not needed in preprod"})
    assert validate(tables, definition) == []
    definition["people"].omit["payload"] = ""
    assert any("omission" in p for p in validate(tables, definition))


def test_type_drift_and_removed_source_columns_are_blocked():
    tables = source_tables()
    tables["people"]["columns"][0]["type"] = "text"
    assert any("type/nullability" in p for p in validate(tables, SCHEMA))
    tables["people"]["columns"].pop()
    assert any("source column is missing" in p for p in validate(tables, SCHEMA))


def test_foreign_keys_require_matching_token_scopes():
    definition = deepcopy(SCHEMA)
    definition["employment"].columns["employee_email"] = Column("employee_email", "text", token_email("wrong-scope"))
    assert any("foreign-key transformations must match" in p for p in validate(source_tables(), definition))


def test_target_schema_can_rename_a_column_without_changing_its_source():
    definition = deepcopy(SCHEMA)
    definition["people"].columns["email_token"] = definition["people"].columns.pop("email")
    definition["people"] = replace(definition["people"], unique=(("email_token",), ("national_id",)))
    definition["employment"] = replace(definition["employment"], foreign_keys=(
        ForeignKey(("company_id",), "companies", ("company_id",)),
        ForeignKey(("employee_email",), "people", ("email_token",)),
    ))
    assert validate(source_tables(), definition) == []
    output = ddl("business", definition)
    assert '"email_token" text NOT NULL' in output
    assert 'REFERENCES "business"."people" ("email_token")' in output
    assert output.index('UNIQUE ("email_token")') < output.index('FOREIGN KEY ("employee_email")')


def test_non_nullable_nulling_and_unknown_rules_are_rejected():
    definition = deepcopy(SCHEMA)
    definition["people"].columns["email"] = Column("email", "text", null())
    assert any("cannot null" in p for p in validate(source_tables(), definition))
    definition["people"].columns["email"] = Column("email", "text", {"action": "guess"})
    assert any("unsupported transformation" in p for p in validate(source_tables(), definition))


def test_new_source_table_cannot_be_silently_ignored():
    tables = source_tables()
    tables["payments"] = {"columns": [], "constraints": []}
    assert any("payments: source table has no target definition" in p for p in validate(tables, SCHEMA))
