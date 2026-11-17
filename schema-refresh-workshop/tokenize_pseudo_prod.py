"""Keyed email/national-ID tokens for pseudo-prod, preserving relationships."""

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets

import psycopg
from psycopg import sql
from psycopg.types.json import Json, Jsonb


KEY_PATH = Path('/keys/pseudo-prod.hmac')
PRIMARY_KEYS = {'people': 'person_id', 'employment': 'contract_id', 'companies': 'company_id'}


def load_key(create=False, path=KEY_PATH):
    if create:
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(secrets.token_bytes(32))
                output.flush()
                os.fsync(output.fileno())
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError('The HMAC key must be 32 bytes; do not replace a key already in use')
    return key


def field_kind(name):
    normalized = name.lower().replace('_', '').replace('-', '')
    if 'email' in normalized:
        return 'email'
    if 'nationalid' in normalized:
        return 'national_id'
    return None


def keyed_digest(key, message):
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def token(value, kind, key):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('Expected a text email or national-ID value')
    digest = keyed_digest(key, (kind + '\0' + value).encode('utf-8'))
    return f'hmac_email_{digest}@example.invalid' if kind == 'email' else f'hmac_nid_{digest}'


def transform_json(value, key, kind=None):
    if isinstance(value, dict):
        return {name: transform_json(item, key, field_kind(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [transform_json(item, key, kind) for item in value]
    return token(value, kind, key) if kind else value


def leaf_count(value, kind=None):
    if isinstance(value, dict):
        return sum(leaf_count(item, field_kind(name)) for name, item in value.items())
    if isinstance(value, list):
        return sum(leaf_count(item, kind) for item in value)
    return int(kind is not None and value is not None)


def specs(connection):
    result = {}
    rows = connection.execute('''SELECT table_name, column_name, data_type
        FROM information_schema.columns WHERE table_schema='business'
        ORDER BY table_name, ordinal_position''').fetchall()
    for table, column, data_type in rows:
        if field_kind(column) or data_type in ('json', 'jsonb'):
            if table not in PRIMARY_KEYS:
                raise ValueError('Review the primary key for a newly discovered PII table')
            result.setdefault(table, []).append((column, data_type))
    return result


def read_rows(connection, table, columns):
    names = [PRIMARY_KEYS[table], *[column for column, _ in columns]]
    cursor = connection.execute(sql.SQL('SELECT {} FROM business.{} ORDER BY {}').format(
        sql.SQL(', ').join(map(sql.Identifier, names)), sql.Identifier(table),
        sql.Identifier(PRIMARY_KEYS[table])))
    return {row[0]: dict(zip(names[1:], row[1:])) for row in cursor}


def expected_rows(rows, columns, key):
    return {identifier: {
        name: transform_json(values[name], key) if data_type in ('json', 'jsonb')
        else token(values[name], field_kind(name), key)
        for name, data_type in columns
    } for identifier, values in rows.items()}


def ensure_target(target, expected_database="pseudo-prod"):
    if target.info.dbname != expected_database:
        raise ValueError('Connection does not match the expected pseudo database')


def verify_expected(target, definitions, source_rows, expected):
    fields = {}
    for table, columns in definitions.items():
        current = read_rows(target, table, columns)
        if current.keys() != expected[table].keys():
            raise ValueError('Source and clone primary-key sets differ')
        for name, data_type in columns:
            fields[f'business.{table}.{name}'] = {
                'values_checked': sum(leaf_count(values[name]) if data_type in ('json', 'jsonb')
                    else int(values[name] is not None) for values in source_rows[table].values()),
                'non_keyed_values': sum(current[identifier][name] != values[name]
                    for identifier, values in expected[table].items()),
            }
    orphans = target.execute('''SELECT count(*) FROM business.employment AS e
        LEFT JOIN business.people AS p ON p.email=e.employee_email
        WHERE p.person_id IS NULL''').fetchone()[0]
    return {'fields': fields, 'non_keyed_values': sum(item['non_keyed_values'] for item in fields.values()),
            'orphaned_employment_links': orphans}


def snapshot(source, target, key):
    definitions = specs(source)
    if definitions != specs(target):
        raise ValueError('Source and clone PII column definitions differ')
    if not definitions or not any(field_kind(name) == 'national_id'
                                 for columns in definitions.values() for name, _ in columns):
        raise ValueError('Expected email and national-ID columns were not found')
    originals = {table: read_rows(source, table, columns) for table, columns in definitions.items()}
    expected = {table: expected_rows(originals[table], columns, key)
                for table, columns in definitions.items()}
    return definitions, originals, expected


def verify_pseudo_prod(source, target, key, *, expected_database="pseudo-prod"):
    ensure_target(target, expected_database)
    with source.transaction(), target.transaction():
        source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        definitions, originals, expected = snapshot(source, target, key)
        return verify_expected(target, definitions, originals, expected)


def tokenize_pseudo_prod(source, target, key, *, expected_database="pseudo-prod"):
    """Update selected identifiers atomically; reruns use source values and the same key."""
    ensure_target(target, expected_database)
    with source.transaction(), target.transaction():
        source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        target.execute("SELECT pg_advisory_xact_lock(hashtext('pseudo-prod-hmac'))")
        target.execute('LOCK TABLE business.people, business.employment IN ACCESS EXCLUSIVE MODE')
        definitions, originals, expected = snapshot(source, target, key)
        pending = {}
        for table, columns in definitions.items():
            current = read_rows(target, table, columns)
            if current.keys() != expected[table].keys():
                raise ValueError('Source and clone primary-key sets differ')
            pending[table] = []
            for identifier, values in current.items():
                for name, _ in columns:
                    if values[name] != originals[table][identifier][name] and values[name] != expected[table][identifier][name]:
                        raise ValueError('A target value matches neither the source nor this key; update aborted')
                if values != expected[table][identifier]:
                    pending[table].append(identifier)

        updated = sum(map(len, pending.values()))
        if updated:
            constraints = target.execute('''SELECT c.conname, t.relname, c.condeferrable, c.condeferred
                FROM pg_constraint AS c JOIN pg_class AS t ON t.oid=c.conrelid
                JOIN pg_namespace AS n ON n.oid=t.relnamespace
                WHERE n.nspname='business' AND c.contype='f' ORDER BY t.relname, c.conname''').fetchall()
            for name, table, deferrable, deferred in constraints:
                target.execute(sql.SQL('ALTER TABLE business.{} ALTER CONSTRAINT {} DEFERRABLE INITIALLY IMMEDIATE').format(
                    sql.Identifier(table), sql.Identifier(name)))
            target.execute('SET CONSTRAINTS ALL DEFERRED')
            for table, identifiers in pending.items():
                columns = definitions[table]
                query = sql.SQL('UPDATE business.{} SET {} WHERE {}=%s').format(
                    sql.Identifier(table), sql.SQL(', ').join(
                        sql.SQL('{}=%s').format(sql.Identifier(name)) for name, _ in columns),
                    sql.Identifier(PRIMARY_KEYS[table]))
                parameters = []
                for identifier in identifiers:
                    values = expected[table][identifier]
                    parameters.append([None if values[name] is None else
                        Jsonb(values[name]) if data_type == 'jsonb' else
                        Json(values[name]) if data_type == 'json' else values[name]
                        for name, data_type in columns] + [identifier])
                with target.cursor() as cursor:
                    cursor.executemany(query, parameters)
            target.execute('SET CONSTRAINTS ALL IMMEDIATE')
            for name, table, deferrable, deferred in constraints:
                mode = 'DEFERRABLE INITIALLY DEFERRED' if deferred else 'DEFERRABLE INITIALLY IMMEDIATE' if deferrable else 'NOT DEFERRABLE'
                target.execute(sql.SQL('ALTER TABLE business.{} ALTER CONSTRAINT {} {}').format(
                    sql.Identifier(table), sql.Identifier(name), sql.SQL(mode)))
        report = verify_expected(target, definitions, originals, expected)
        if report['non_keyed_values'] or report['orphaned_employment_links']:
            raise ValueError('Token verification or relationship validation failed; update aborted')
        return {**report, 'updated_rows': updated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['tokenize', 'verify'])
    args = parser.parse_args()
    key = load_key(create=args.command == 'tokenize')
    with psycopg.connect(os.environ['SOURCE_DSN'], autocommit=True) as source, \
         psycopg.connect(os.environ['PSEUDO_PROD_DSN'], autocommit=True) as target:
        operation = tokenize_pseudo_prod if args.command == 'tokenize' else verify_pseudo_prod
        report = operation(source, target, key)
    print(json.dumps(report, indent=2))
    return int(bool(report['non_keyed_values'] or report['orphaned_employment_links']))


if __name__ == '__main__':
    raise SystemExit(main())
