"""Transform before COPY and atomically publish only constraint-valid staging."""

from datetime import date
import hashlib
import hmac
import uuid

from psycopg import sql
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb


def transform(value, rule, key, type_name):
    if value is None:
        return None
    action = rule["action"]
    if action == "keep":
        return value
    if action == "null":
        return None
    if action == "constant":
        result = rule["value"]
        return date.fromisoformat(result) if type_name == "date" else result
    if action in {"token_email", "token_id"}:
        token = hmac.new(key, (rule["scope"] + "\0" + str(value)).encode(), hashlib.sha256).hexdigest()[:32]
        return f"person-{token}@example.invalid" if action == "token_email" else f"id-{token}"
    raise ValueError("Unsupported transform")


def identifiers(names):
    return sql.SQL(", ").join(sql.Identifier(name) for name in names)


def publish(source, target, tables, actions, key, destination="business"):
    if destination not in {"business", "legacy"}:
        raise ValueError("Unknown destination")
    stage = "stage_" + uuid.uuid4().hex[:12]
    counts = {}
    with target.transaction():
        target.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(stage)))
        target.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(sql.Identifier(stage)))
        for table_name, table in tables.items():
            definitions = [sql.SQL("{} {} {}").format(
                sql.Identifier(column["column_name"]), sql.SQL(column["type"]),
                sql.SQL("" if column["nullable"] else "NOT NULL")) for column in table["columns"]]
            target.execute(sql.SQL("CREATE TABLE {} ({})").format(
                sql.Identifier(stage, table_name), sql.SQL(", ").join(definitions)))
            columns = [column["column_name"] for column in table["columns"]]
            with source.cursor(name="read_" + uuid.uuid4().hex[:8], row_factory=tuple_row) as reader:
                reader.execute(sql.SQL("SELECT {} FROM {}").format(identifiers(columns), sql.Identifier("business", table_name)))
                with target.cursor().copy(sql.SQL("COPY {} ({}) FROM STDIN").format(
                        sql.Identifier(stage, table_name), identifiers(columns))) as writer:
                    count = 0
                    for row in reader:
                        output = []
                        for column, value in zip(table["columns"], row):
                            rule = actions[f"{table_name}.{column['column_name']}"]
                            sanitized = transform(value, rule, key, column["type"])
                            output.append(Jsonb(sanitized) if column["type"] == "jsonb" and sanitized is not None else sanitized)
                        writer.write_row(output)
                        count += 1
                counts[table_name] = count
        # Validate all constraints after every table has been populated.
        ordered_constraints = [(table_name, constraint) for table_name, table in tables.items()
                               for constraint in table["constraints"]]
        ordered_constraints.sort(key=lambda item: item[1]["kind"] == "f")
        for table_name, constraint in ordered_constraints:
            kind = constraint["kind"]
            if kind == "f":
                definition = sql.SQL("FOREIGN KEY ({}) REFERENCES {} ({})").format(
                    identifiers(constraint["columns"]), sql.Identifier(stage, constraint["referenced_table"]),
                    identifiers(constraint["referenced_columns"]))
            elif kind in {"p", "u"}:
                definition = sql.SQL("{} ({})").format(sql.SQL("PRIMARY KEY" if kind == "p" else "UNIQUE"),
                                                      identifiers(constraint["columns"]))
            else:
                definition = sql.SQL(constraint["definition"])
            target.execute(sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} {}").format(
                sql.Identifier(stage, table_name), sql.Identifier(constraint["name"]), definition))
        for table_name, expected in counts.items():
            actual = target.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(stage, table_name))).fetchone()[0]
            if actual != expected:
                raise ValueError("Row-count validation failed")
        target.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(destination)))
        target.execute(sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(sql.Identifier(stage), sql.Identifier(destination)))
        if destination == "business":
            target.execute("GRANT USAGE ON SCHEMA business TO preprod_viewer")
            target.execute("GRANT SELECT ON ALL TABLES IN SCHEMA business TO preprod_viewer")
    return counts
