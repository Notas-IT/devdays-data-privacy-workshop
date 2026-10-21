"""Code-defined target tables with an explicit decision for every source column."""

from dataclasses import dataclass, field
import re
import uuid

from psycopg import sql
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb

from clone import transform


@dataclass(frozen=True)
class Column:
    source: str
    pg_type: str
    rule: dict
    nullable: bool = False


@dataclass(frozen=True)
class ForeignKey:
    columns: tuple
    table: str
    references: tuple


@dataclass(frozen=True)
class Table:
    source: str
    columns: dict
    primary_key: tuple
    unique: tuple = ()
    foreign_keys: tuple = ()
    checks: tuple = ()
    omit: dict = field(default_factory=dict)


def keep(*, domain=None):
    return {"action": "keep", **({"domain": sorted(domain)} if domain is not None else {})}


def constant(value):
    return {"action": "constant", "value": value}


def null():
    return {"action": "null"}


def token_email(scope="email"):
    return {"action": "token_email", "scope": scope}


def token_id(scope):
    return {"action": "token_id", "scope": scope}


def validate(tables, definition):
    problems = []
    if not definition:
        return ["Target schema has no tables"]
    source_names = [table.source for table in definition.values()]
    if len(source_names) != len(set(source_names)):
        problems.append("Each source table must map to exactly one target table")
    for name in sorted(set(tables) - set(source_names)):
        problems.append(f"{name}: source table has no target definition")
    for target_name, table in sorted(definition.items()):
        if table.source not in tables:
            problems.append(f"{table.source}: source table is missing")
            continue
        source = {column["column_name"]: column for column in tables[table.source]["columns"]}
        mapped = [column.source for column in table.columns.values()]
        if len(mapped) != len(set(mapped)) or set(mapped) & set(table.omit):
            problems.append(f"{target_name}: source column mapped more than once")
        for name in sorted(set(source) - set(mapped) - set(table.omit)):
            problems.append(f"{table.source}.{name}: no column rule; add a mapping or an explicit omission")
        for name, reason in table.omit.items():
            if name not in source or not isinstance(reason, str) or not reason.strip():
                problems.append(f"{table.source}.{name}: omission needs an existing column and a reason")
        for name, column in sorted(table.columns.items()):
            key = f"{table.source}.{column.source} -> {target_name}.{name}"
            if column.source not in source:
                problems.append(f"{key}: source column is missing")
                continue
            if source[column.source]["type"] != column.pg_type or source[column.source]["nullable"] != column.nullable:
                problems.append(f"{key}: source type/nullability differs from the code definition")
            if not re.fullmatch(r"text|bigint|integer|date|boolean|jsonb|numeric(?:\(\d+,\d+\))?", column.pg_type):
                problems.append(f"{key}: unsupported target type")
            action = column.rule.get("action")
            if action not in {"keep", "constant", "null", "token_email", "token_id"}:
                problems.append(f"{key}: unsupported transformation")
            if action == "constant" and "value" not in column.rule:
                problems.append(f"{key}: constant needs a value")
            if action == "null" and not column.nullable:
                problems.append(f"{key}: cannot null a NOT NULL column")
            if action in {"token_email", "token_id"} and (column.pg_type != "text" or not column.rule.get("scope")):
                problems.append(f"{key}: token transformation needs text and a shared scope")
            if "domain" in column.rule and (action != "keep" or not column.rule["domain"]):
                problems.append(f"{key}: domain restriction needs keep and a nonempty domain")
        if not table.columns or not table.primary_key:
            problems.append(f"{target_name}: define columns and a primary key")
        for group in (table.primary_key, *table.unique):
            if not group or any(name not in table.columns for name in group):
                problems.append(f"{target_name}: key refers to an undefined target column")
        for name in table.primary_key:
            if name in table.columns and table.columns[name].nullable:
                problems.append(f"{target_name}.{name}: primary key must be NOT NULL")
        for fk in table.foreign_keys:
            other = definition.get(fk.table)
            if (not other or not fk.columns or len(fk.columns) != len(fk.references)
                    or any(name not in table.columns for name in fk.columns)
                    or any(name not in other.columns for name in fk.references)):
                problems.append(f"{target_name}: foreign key refers to undefined target columns")
                continue
            if fk.references not in (other.primary_key, *other.unique):
                problems.append(f"{target_name}: foreign key must reference a primary or unique key")
            for local, remote in zip(fk.columns, fk.references):
                a, b = table.columns[local], other.columns[remote]
                if a.pg_type != b.pg_type or a.rule != b.rule:
                    problems.append(f"{target_name}.{local}: foreign-key transformations must match {fk.table}.{remote}")
    return problems


def names(values):
    return sql.SQL(", ").join(sql.Identifier(value) for value in values)


def statements(schema, definition):
    """DDL comes only from reviewed Python code, never production constraint text."""
    foreign_keys = []
    for name, table in sorted(definition.items()):
        columns = [sql.SQL("{} {}{}").format(sql.Identifier(column_name), sql.SQL(column.pg_type),
                   sql.SQL("" if column.nullable else " NOT NULL"))
                   for column_name, column in sorted(table.columns.items())]
        yield sql.SQL("CREATE TABLE {} ({});").format(sql.Identifier(schema, name), sql.SQL(", ").join(columns))
    for name, table in sorted(definition.items()):
        constraints = [sql.SQL("PRIMARY KEY ({})").format(names(table.primary_key))]
        constraints += [sql.SQL("UNIQUE ({})").format(names(group)) for group in table.unique]
        # CHECK expressions are trusted application code in preprod_schema.py.
        constraints += [sql.SQL("CHECK ({})").format(sql.SQL(expression)) for expression in table.checks]
        foreign_keys.extend((name, fk) for fk in table.foreign_keys)
        for constraint in constraints:
            yield sql.SQL("ALTER TABLE {} ADD {};").format(sql.Identifier(schema, name), constraint)
    # Referenced unique/primary keys must exist before any foreign key.
    for name, fk in foreign_keys:
        yield sql.SQL("ALTER TABLE {} ADD FOREIGN KEY ({}) REFERENCES {} ({});").format(
            sql.Identifier(schema, name), names(fk.columns), sql.Identifier(schema, fk.table), names(fk.references))


def ddl(schema, definition):
    create = sql.SQL("CREATE SCHEMA {};").format(sql.Identifier(schema)).as_string()
    return create + "\n" + "\n".join(statement.as_string() for statement in statements(schema, definition)) + "\n"


def mapping_text(definition):
    lines = ["SOURCE -> TARGET | TYPE | RULE", ""]
    for name, table in sorted(definition.items()):
        for column_name, column in sorted(table.columns.items()):
            action = column.rule["action"]
            detail = f" scope={column.rule['scope']}" if "scope" in column.rule else ""
            if action == "constant":
                detail = f" value={column.rule['value']!r}"
            if "domain" in column.rule:
                detail += f" domain={column.rule['domain']!r}"
            lines.append(f"{table.source}.{column.source} -> {name}.{column_name} | {column.pg_type} | {action}{detail}")
        for source, reason in sorted(table.omit.items()):
            lines.append(f"{table.source}.{source} -> OMIT | {reason}")
    return "\n".join(lines) + "\n"


def publish(source, target, tables, definition, key, *, source_schema="business", target_schema="business", viewer="preprod_viewer"):
    problems = validate(tables, definition)
    if problems:
        raise ValueError("Invalid source-to-target contract")
    stage = "stage_" + uuid.uuid4().hex[:12]
    counts = {}
    with target.transaction():
        target.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(stage)))
        target.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(sql.Identifier(stage)))
        ddl_statements = list(statements(stage, definition))
        for statement in ddl_statements[:len(definition)]:
            target.execute(statement)
        for name, table in sorted(definition.items()):
            columns = sorted(table.columns.items())
            with source.cursor(name="contract_" + uuid.uuid4().hex[:8], row_factory=tuple_row) as reader:
                reader.execute(sql.SQL("SELECT {} FROM {}").format(
                    names(column.source for _, column in columns), sql.Identifier(source_schema, table.source)))
                with target.cursor().copy(sql.SQL("COPY {} ({}) FROM STDIN").format(
                        sql.Identifier(stage, name), names(column_name for column_name, _ in columns))) as writer:
                    count = 0
                    for row in reader:
                        output = []
                        for value, (_, column) in zip(row, columns):
                            if value is not None and "domain" in column.rule and str(value) not in column.rule["domain"]:
                                raise ValueError("Value escaped an explicitly permitted domain")
                            sanitized = transform(value, column.rule, key, column.pg_type)
                            output.append(Jsonb(sanitized) if column.pg_type == "jsonb" and sanitized is not None else sanitized)
                        writer.write_row(output)
                        count += 1
                counts[name] = count
        # All tables exist before foreign keys are installed.
        for statement in ddl_statements[len(definition):]:
            target.execute(statement)
        for name, count in counts.items():
            actual = target.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(stage, name))).fetchone()[0]
            if actual != count:
                raise ValueError("Row-count validation failed")
        target.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(target_schema)))
        target.execute(sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(sql.Identifier(stage), sql.Identifier(target_schema)))
        target.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(target_schema), sql.Identifier(viewer)))
        target.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(sql.Identifier(target_schema), sql.Identifier(viewer)))
    return counts
