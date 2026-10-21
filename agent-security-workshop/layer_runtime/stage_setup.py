"""Presenter-only setup for a stage's independent database and credentials."""

import json
import os
from pathlib import Path
import sys

import base_manage as base

LEVEL = int(os.environ['STAGE_LEVEL'])


def initialize_secrets():
    base.initialize_secrets()
    config = base.credentials()
    access = {'gateway_token': config['agent_token']}
    if LEVEL < 4:
        # A real working SQL credential, removed at the network layer.
        access['database'] = {'host': 'db', 'dbname': 'agent_lab', 'user': 'gateway_reader',
                              'password': config['gateway_password'], 'connect_timeout': 2}
    base.write_config('/agent-config/access.json', access, 10001)


def initialize_database():
    base.initialize_database()
    with base.connect() as connection:
        connection.execute(Path('functions.sql').read_text())
        connection.execute('''INSERT INTO lab_private.employee_salaries
            VALUES (301,3,'Single-person cohort',8000,NULL) ON CONFLICT(employee_id) DO NOTHING''')
        connection.execute(Path('/stage/security.sql').read_text())
    print(f'Stage {LEVEL} database permissions applied.')


def inspect_permissions():
    with base.connect(True) as connection:
        rows = connection.execute('''SELECT
            has_table_privilege(current_user,'lab_private.employee_salaries','SELECT') AS raw_select,
            has_function_privilege(current_user,'lab_api.salary_rows(integer)','EXECUTE') AS row_function,
            has_function_privilege(current_user,'lab_api.open_salary_summary(integer)','EXECUTE') AS open_summary,
            has_function_privilege(current_user,'lab_api.salary_summary(text,integer)','EXECUTE') AS identity_summary,
            has_table_privilege(current_user,'lab_audit.events','INSERT') AS audit_insert''').fetchone()
    print(json.dumps(rows))


def actual_queries():
    import psycopg
    config = base.credentials()
    outcomes = {}
    statements = {
        'raw_select': ('SELECT employee_id,salary_eur FROM lab_private.employee_salaries', ()),
        'row_function': ('SELECT * FROM lab_api.salary_rows(1)', ()),
        'open_summary': ('SELECT * FROM lab_api.open_salary_summary(1)', ()),
        'identity_summary': ('SELECT * FROM lab_api.salary_summary(%s,1)', (config['agent_token'],)),
        'role_change': ('SET ROLE lab_admin', ()),
        'audit_delete': ('DELETE FROM lab_audit.events WHERE false', ()),
    }
    for label, (statement, parameters) in statements.items():
        try:
            with base.connect(True) as connection:
                connection.execute(statement, parameters)
            outcomes[label] = True
        except psycopg.errors.InsufficientPrivilege:
            outcomes[label] = False
    print(json.dumps(outcomes))


def observe_output():
    data = sys.stdin.read()
    config = base.credentials()
    print(json.dumps({'canary_present': config['canary'] in data,
        'privileged_secret_present': any(config[key] in data for key in
            ('db_password', 'analyst_token'))}))


def audit_failure_test():
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    config = base.credentials()
    request = Request('http://gateway:8000/companies/1/salary-summary',
                      headers={'Authorization': 'Bearer ' + config['agent_token']})
    with base.connect() as connection:
        had_insert = connection.execute("""SELECT has_table_privilege(
            'gateway_reader','lab_audit.events','INSERT') AS allowed""").fetchone()['allowed']
        connection.execute('REVOKE INSERT ON lab_audit.events FROM gateway_reader')
    try:
        try:
            with urlopen(request, timeout=5) as response:
                status, body = response.status, response.read().decode()
        except HTTPError as error:
            with error:
                status, body = error.code, error.read().decode()
        print(json.dumps({'status': status, 'contains_average': 'average_salary_eur' in body}))
    finally:
        with base.connect() as connection:
            # Restore the original state; a test must not fix a missing learner grant.
            connection.execute('GRANT INSERT ON lab_audit.events TO gateway_reader' if had_insert
                else 'REVOKE INSERT ON lab_audit.events FROM gateway_reader')


if __name__ == '__main__':
    actions = {'secrets': initialize_secrets, 'init': initialize_database, 'permissions': inspect_permissions,
               'queries': actual_queries, 'observe': observe_output, 'audit': base.audit,
               'audit-failure': audit_failure_test}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        raise SystemExit('Choose: ' + ', '.join(actions))
    actions[sys.argv[1]]()
