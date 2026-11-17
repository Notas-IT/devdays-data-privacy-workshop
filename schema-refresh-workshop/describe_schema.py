"""Export table/column/type metadata in a deterministic, alphabetically sorted file."""

import argparse
import os
from pathlib import Path

import psycopg


def read_schema(connection, schemas=None):
    with connection.transaction():
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        connection.execute('SET LOCAL search_path = pg_catalog')
        return connection.execute('''SELECT n.nspname, c.relname, a.attname,
                pg_catalog.format_type(a.atttypid, a.atttypmod)
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid=c.relnamespace
            LEFT JOIN pg_catalog.pg_attribute AS a
              ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
            WHERE c.relkind IN ('r', 'p', 'f')
              AND n.nspname <> 'information_schema' AND n.nspname NOT LIKE 'pg\\_%%' ESCAPE '\\'
              AND (%s::text[] IS NULL OR n.nspname=ANY(%s::text[]))''',
            (schemas, schemas)).fetchall()


def render_schema(rows):
    tables = {}
    for schema, table, column, data_type in rows:
        columns = tables.setdefault((schema, table), {})
        if column is not None:
            columns[column] = data_type
    sections = []
    for (schema, table), columns in sorted(tables.items()):
        lines = [f'{schema}.{table}']
        lines.extend(f'  {column}: {data_type}' for column, data_type in sorted(columns.items()))
        sections.append('\n'.join(lines))
    return '\n\n'.join(sections) + ('\n' if sections else '')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn-env', default='PSEUDO_PROD_DSN', help='Environment variable containing the connection string')
    parser.add_argument('--schema', action='append', help='Limit export to this schema; may be repeated')
    parser.add_argument('--output', type=Path, default=Path('pseudo-prod.schema.txt'))
    args = parser.parse_args()
    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        parser.error(f'{args.dsn_env} is not set')
    with psycopg.connect(dsn, autocommit=True) as connection:
        rows = read_schema(connection, args.schema)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_schema(rows), encoding='utf-8', newline='\n')
    tables = {(schema, table) for schema, table, _, _ in rows}
    columns = sum(column is not None for _, _, column, _ in rows)
    print(f'Wrote {args.output}: {len(tables)} tables, {columns} columns.')


if __name__ == '__main__':
    main()
