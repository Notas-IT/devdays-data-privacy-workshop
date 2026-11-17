"""Refresh pseudo-prod only when table/column/type descriptions match."""

import argparse
import difflib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from describe_schema import read_schema, render_schema
from mask_pseudo_prod import mask_pseudo_prod
from tokenize_pseudo_prod import ensure_target, load_key, tokenize_pseudo_prod


class SchemaMismatch(ValueError):
    """A refresh requires schema review first; the target was not replaced."""


def description(dsn):
    with psycopg.connect(dsn, autocommit=True) as connection:
        return render_schema(read_schema(connection))


def database_dsn(dsn, name):
    return make_conninfo(dsn, dbname=name)


def postgres_tool(tool, dsn, *arguments):
    # Keep passwords out of command-line arguments and error messages.
    settings = conninfo_to_dict(dsn)
    environment = os.environ.copy()
    for option, variable in [('host', 'PGHOST'), ('port', 'PGPORT'),
                             ('user', 'PGUSER'), ('password', 'PGPASSWORD'),
                             ('dbname', 'PGDATABASE'), ('sslmode', 'PGSSLMODE')]:
        if option in settings:
            environment[variable] = settings[option]
    result = subprocess.run([tool, *arguments], env=environment, capture_output=True)
    if result.returncode:
        # PostgreSQL diagnostics can contain failing rows; do not expose them.
        raise RuntimeError(f'{tool} failed (exit {result.returncode}); refresh cancelled')


def row_counts(connection):
    tables = sorted({(schema, table) for schema, table, _, _ in read_schema(connection)})
    return {f'{schema}.{table}': connection.execute(
        sql.SQL('SELECT count(*) FROM {}.{}').format(sql.Identifier(schema), sql.Identifier(table))
    ).fetchone()[0] for schema, table in tables}


def publish(admin, target_name, stage_name, backup_name):
    # PostgreSQL rolls both renames back if either fails (including active clients).
    # Do not disconnect other users to force a refresh.
    with admin.transaction():
        admin.execute("SET LOCAL lock_timeout = '5s'")
        admin.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(
            sql.Identifier(target_name), sql.Identifier(backup_name)))
        admin.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(
            sql.Identifier(stage_name), sql.Identifier(target_name)))


def refresh(source_dsn, target_dsn, key_path, artifacts, *, expected_database='pseudo-prod'):
    """Stage, sanitise and validate before replacing the named target.

    expected_database is explicit for isolated integration tests; the CLI always
    requires pseudo-prod. No connection to the source is used to write data.
    """
    artifacts = Path(artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    source_settings, target_settings = map(conninfo_to_dict, (source_dsn, target_dsn))
    if all(source_settings.get(k) == target_settings.get(k) for k in ('host', 'port', 'dbname')):
        raise ValueError('Source and target must be separate databases')
    target_name = target_settings['dbname']
    with psycopg.connect(target_dsn, autocommit=True) as target:
        ensure_target(target, expected_database)

    with psycopg.connect(database_dsn(target_dsn, 'postgres'), autocommit=True) as admin:
        # Serialise this workflow, including the schema check and publication.
        admin.execute('SELECT pg_advisory_lock(hashtext(%s))', ('refresh-' + target_name,))
        original, previous = description(source_dsn), description(target_dsn)
        (artifacts / 'original.schema.txt').write_text(original, encoding='utf-8')
        (artifacts / 'pseudo-prod.schema.txt').write_text(previous, encoding='utf-8')
        difference = ''.join(difflib.unified_diff(previous.splitlines(True), original.splitlines(True),
            fromfile='pseudo-prod', tofile='original'))
        (artifacts / 'schema.diff').write_text(difference, encoding='utf-8')
        if difference:
            raise SchemaMismatch('Schemas differ; pseudo-prod was left unchanged. See ' + str(artifacts / 'schema.diff'))

        # Reuse the persistent key. A missing key must not silently change existing tokens.
        key = load_key(path=Path(key_path))
        suffix = uuid.uuid4().hex
        stage_name, backup_name = 'pseudo_stage_' + suffix, 'pseudo_backup_' + suffix
        stage_dsn = database_dsn(target_dsn, stage_name)
        created = False
        published = False
        try:
            admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(stage_name)))
            created = True
            # Raw staging data is accessible only to its owner/admin, never PUBLIC.
            admin.execute(sql.SQL('REVOKE CONNECT ON DATABASE {} FROM PUBLIC').format(sql.Identifier(stage_name)))
            with tempfile.TemporaryDirectory(prefix='pseudo-refresh-') as temporary:
                archive = Path(temporary) / 'database.dump'
                postgres_tool('pg_dump', source_dsn, '--format=custom', '--no-owner', '--no-acl',
                              '--file', str(archive))
                postgres_tool('pg_restore', stage_dsn, '--single-transaction', '--exit-on-error',
                              '--no-owner', '--no-acl', '--dbname', stage_name, str(archive))
            if description(stage_dsn) != original:
                raise SchemaMismatch('Source schema changed during cloning; pseudo-prod was left unchanged')
            with psycopg.connect(source_dsn, autocommit=True) as source, \
                 psycopg.connect(stage_dsn, autocommit=True) as stage:
                counts = row_counts(stage)
                if counts != row_counts(source):
                    raise ValueError('Source/clone row counts differ; refresh cancelled')
                tokens = tokenize_pseudo_prod(source, stage, key, expected_database=stage_name)
                masking = mask_pseudo_prod(stage, expected_database=stage_name)
                if row_counts(stage) != counts:
                    raise ValueError('Anonymisation changed row counts; refresh cancelled')
            # Recheck the current target so concurrent schema changes cannot be overwritten.
            if description(target_dsn) != previous:
                raise SchemaMismatch('Target schema changed during refresh; pseudo-prod was left unchanged')
            publish(admin, target_name, stage_name, backup_name)
            published = True
            report = {'status': 'refreshed', 'row_counts': counts,
                      'non_keyed_values': tokens['non_keyed_values'],
                      'unmasked_values': masking['total_unmasked_values']}
            try:
                admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(backup_name)))
            except psycopg.Error:
                report['retained_backup'] = backup_name
            return report
        finally:
            if created and not published:
                admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(stage_name)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, default=Path('artifacts/refresh'))
    parser.add_argument('--key-file', type=Path, default=Path('/keys/pseudo-prod.hmac'))
    args = parser.parse_args()
    try:
        report = refresh(os.environ['SOURCE_DSN'], os.environ['PSEUDO_PROD_DSN'],
                         args.key_file, args.artifacts)
    except SchemaMismatch as error:
        print('BLOCKED:', error)
        return 2
    except (ValueError, OSError, psycopg.Error, RuntimeError) as error:
        # Database errors may include personal values or connection details.
        print(f'FAIL: refresh cancelled ({type(error).__name__}); pseudo-prod was not replaced')
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
