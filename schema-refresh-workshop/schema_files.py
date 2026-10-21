"""Deterministic, data-free production schema snapshots and file comparisons."""

import argparse
import json
from pathlib import Path
import uuid
import hashlib


def snapshot(tables, schema="business"):
    return {
        "format_version": 1,
        "schema": schema,
        "tables": [
            {"name": name, "kind": table.get("kind", "r"),
             "columns": [{key: value for key, value in column.items() if key != "table_name"}
                         for column in sorted(table["columns"], key=lambda item: item["column_name"])],
             "constraints": [
                 {**{key: value for key, value in constraint.items() if key != "definition"},
                  "definition_hash": hashlib.sha256(constraint["definition"].encode()).hexdigest()}
                 for constraint in sorted(table["constraints"], key=lambda item: item["name"])]}
            for name, table in sorted(tables.items())
        ],
    }


def text_schema(document):
    lines = []
    for table in document["tables"]:
        lines.append(f"{document['schema']}.{table['name']}")
        for column in table["columns"]:
            suffix = "NULL" if column["nullable"] else "NOT NULL"
            lines.append(f"  {column['column_name']}: {column['type']} {suffix}")
        lines.append("")
    return "\n".join(lines)


def compare(previous, current):
    """A rename deliberately appears as removal + addition; never guess mappings."""
    if previous is None:
        return {"baseline": True, "changed": False, "changes": []}
    if previous["format_version"] != 1 or current["format_version"] != 1:
        raise ValueError("Unsupported schema snapshot version")
    changes = []
    if previous["schema"] != current["schema"]:
        changes.append({"kind": "schema_changed", "before": previous["schema"], "after": current["schema"]})
    old = {table["name"]: table for table in previous["tables"]}
    new = {table["name"]: table for table in current["tables"]}
    for name in sorted(old.keys() | new.keys()):
        if name not in old or name not in new:
            changes.append({"kind": "table_added" if name in new else "table_removed", "table": name,
                            "definition": new.get(name, old.get(name))})
            continue
        if old[name].get("kind", "r") != new[name].get("kind", "r"):
            changes.append({"kind": "table_kind_changed", "table": name,
                            "before": old[name].get("kind", "r"), "after": new[name].get("kind", "r")})
        old_columns = {c["column_name"]: c for c in old[name]["columns"]}
        new_columns = {c["column_name"]: c for c in new[name]["columns"]}
        for column in sorted(old_columns.keys() | new_columns.keys()):
            before, after = old_columns.get(column), new_columns.get(column)
            if before == after:
                continue
            kind = "column_added" if before is None else "column_removed" if after is None else "column_changed"
            changes.append({"kind": kind, "table": name, "column": column, "before": before, "after": after})
        if old[name]["constraints"] != new[name]["constraints"]:
            changes.append({"kind": "constraints_changed", "table": name,
                            "before": old[name]["constraints"], "after": new[name]["constraints"]})
    return {"baseline": False, "changed": bool(changes), "changes": changes}


def atomic_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def write_json(path, document):
    atomic_text(path, json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def write_snapshot(path, document):
    path = Path(path)
    write_json(path, document)
    atomic_text(path.with_suffix(".txt"), text_schema(document))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = compare(json.loads(args.previous.read_text()), json.loads(args.current.read_text()))
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["changed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
