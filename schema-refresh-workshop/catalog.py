"""Read schema signatures without storing raw defaults or sampled values."""

import hashlib
import json
import re
from psycopg import sql
from psycopg.rows import dict_row


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def inventory(connection):
    with connection.cursor(row_factory=dict_row) as cursor:
        columns = cursor.execute("""
            SELECT c.relname AS table_name, a.attname AS column_name,
                   format_type(a.atttypid, a.atttypmod) AS type,
                   NOT a.attnotnull AS nullable,
                   pg_get_expr(d.adbin, d.adrelid) AS default_expression,
                   a.attidentity AS identity, a.attgenerated AS generated
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
            WHERE n.nspname = 'business' AND c.relkind = 'r'
              AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY c.relname, a.attnum
        """).fetchall()
        constraints = cursor.execute("""
            SELECT c.relname AS table_name, co.conname AS name, co.contype AS kind,
                   pg_get_constraintdef(co.oid) AS definition,
                   ARRAY(SELECT attname FROM pg_attribute
                         WHERE attrelid = co.conrelid AND attnum = ANY(co.conkey)
                         ORDER BY array_position(co.conkey, attnum)) AS columns,
                   rn.nspname AS referenced_schema, rc.relname AS referenced_table,
                   ARRAY(SELECT attname FROM pg_attribute
                         WHERE attrelid = co.confrelid AND attnum = ANY(co.confkey)
                         ORDER BY array_position(co.confkey, attnum)) AS referenced_columns
            FROM pg_constraint co JOIN pg_class c ON c.oid = co.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_class rc ON rc.oid = co.confrelid
            LEFT JOIN pg_namespace rn ON rn.oid = rc.relnamespace
            WHERE n.nspname = 'business' ORDER BY c.relname, co.conname
        """).fetchall()
    tables = {}
    for column in columns:
        expression = column.pop("default_expression")
        column["default_hash"] = digest(expression) if expression is not None else None
        tables.setdefault(column["table_name"], {"columns": [], "constraints": []})["columns"].append(column)
    for constraint in constraints:
        tables[constraint["table_name"]]["constraints"].append(constraint)
    return tables


def column_signature(column):
    return {key: value for key, value in column.items() if key != "table_name"}


def constraint_signature(table):
    return digest(table["constraints"])


def validate_supported_schema(tables):
    if not tables:
        raise ValueError("No business tables found")
    for table in tables.values():
        for column in table["columns"]:
            if not re.fullmatch(r"text|bigint|integer|date|boolean|jsonb|numeric(?:\(\d+,\d+\))?", column["type"]):
                raise ValueError("Unsupported PostgreSQL type requires explicit implementation")
            if column["default_hash"] is not None or column["identity"] or column["generated"]:
                raise ValueError("Defaults, identity, and generated columns require explicit implementation")
        for constraint in table["constraints"]:
            if constraint["kind"] not in {"p", "u", "f", "c"}:
                raise ValueError("Unsupported constraint")
            if constraint["kind"] == "f" and constraint["referenced_schema"] != "business":
                raise ValueError("Cross-schema foreign key cannot be cloned")


def samples(connection, table_name, column, limit=100):
    field = sql.Identifier(column["column_name"])
    table = sql.Identifier("business", table_name)
    # NULL-only rows do not hide a sparsely populated new field.
    query = sql.SQL("SELECT DISTINCT {}::text FROM {} WHERE {} IS NOT NULL LIMIT %s").format(field, table, field)
    return [row[0] for row in connection.execute(query, (limit,)).fetchall()]


def full_domain_is_safe(connection, table_name, column, allowed):
    field = sql.Identifier(column["column_name"])
    query = sql.SQL("SELECT NOT EXISTS (SELECT 1 FROM {} WHERE {} IS NOT NULL AND NOT ({}::text = ANY(%s)))").format(
        sql.Identifier("business", table_name), field, field)
    return connection.execute(query, (list(allowed),)).fetchone()[0]
