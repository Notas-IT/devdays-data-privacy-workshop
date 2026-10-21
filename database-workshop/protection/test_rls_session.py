"""Exercise real RLS with request context on the restricted API connection.

Only setup and expected results use an administrator. Queries under test have
no company WHERE clause: PostgreSQL must apply the account's memberships.
"""

import os
import uuid

import psycopg
from psycopg.rows import dict_row
import pytest

from storage import database, settings


AVERAGES = """SELECT company_registration_number, count(*) AS employees,
    avg(salary_eur) AS average_salary_eur
    FROM private_db.employment_contract
    GROUP BY company_registration_number ORDER BY company_registration_number"""


def admin_db():
    return psycopg.connect(os.environ["ADMIN_DSN"], row_factory=dict_row)


@pytest.fixture
def company_actors():
    """Create fresh accounts with memberships and expectations from loaded data."""
    account_ids = []
    with admin_db() as connection:
        companies = connection.execute(AVERAGES + " LIMIT 2").fetchall()
        assert len(companies) == 2, "Load the workshop dataset with at least two companies"
        actors = []
        for company in companies:
            account_id = connection.execute("""INSERT INTO access_control.accounts
                (username, password_hash, salary_scope)
                VALUES (%s, %s, 'company') RETURNING account_id""",
                ("test_rls_" + uuid.uuid4().hex, "!disabled-test-login")).fetchone()["account_id"]
            account_ids.append(account_id)
            connection.execute("""INSERT INTO access_control.company_memberships
                (account_id, registration_number) VALUES (%s, %s)""",
                (account_id, company["company_registration_number"]))
            actors.append({"account_id": account_id, "expected": company})
    try:
        yield actors
    finally:
        with admin_db() as connection:
            connection.execute("DELETE FROM access_control.accounts WHERE account_id = ANY(%s)",
                               (account_ids,))


def set_actor(connection, actor):
    # Equivalent to SET LOCAL, with a bound value rather than interpolated SQL.
    connection.execute("SELECT set_config('app.account_id', %s, true)",
                       (str(actor["account_id"]),))


@pytest.mark.parametrize("company_index", [0, 1], ids=["first-company", "second-company"])
def test_average_uses_transaction_context(company_actors, company_index):
    actor = company_actors[company_index]
    # This is the same helper that authenticated API requests use.
    with database(actor["account_id"]) as connection:
        role = connection.execute("""SELECT session_user AS login, rolsuper, rolbypassrls,
            c.relowner = r.oid AS owns_salaries, c.relrowsecurity
            FROM pg_roles r CROSS JOIN pg_class c
            WHERE r.rolname = current_user
              AND c.oid = 'private_db.employment_contract'::regclass""").fetchone()
        assert role["login"] == "privacy_api"
        assert not role["rolsuper"] and not role["rolbypassrls"] and not role["owns_salaries"]
        assert role["relrowsecurity"]
        assert connection.execute(AVERAGES).fetchall() == [actor["expected"]]


def test_missing_context_returns_no_salary_data():
    with database() as connection:
        assert connection.execute(AVERAGES).fetchall() == []
        row = connection.execute("""SELECT count(*) AS employees, avg(salary_eur) AS average
            FROM private_db.employment_contract""").fetchone()
        assert row == {"employees": 0, "average": None}


@pytest.mark.parametrize("context", ["", "not-an-account", "9223372036854775808"],
                         ids=["empty", "malformed", "unknown"])
def test_invalid_context_returns_no_salary_data(context):
    with database() as connection:
        connection.execute("SELECT set_config('app.account_id', %s, true)", (context,))
        assert connection.execute(AVERAGES).fetchall() == []


@pytest.mark.parametrize("restriction", ["inactive", "no-membership", "no-salary-permission"])
def test_account_permissions_still_apply_to_context(company_actors, restriction):
    actor = company_actors[0]
    with admin_db() as connection:
        if restriction == "inactive":
            connection.execute("UPDATE access_control.accounts SET active=false WHERE account_id=%s",
                               (actor["account_id"],))
        elif restriction == "no-membership":
            connection.execute("DELETE FROM access_control.company_memberships WHERE account_id=%s",
                               (actor["account_id"],))
        else:
            connection.execute("UPDATE access_control.accounts SET salary_scope='none' WHERE account_id=%s",
                               (actor["account_id"],))
    with database(actor["account_id"]) as connection:
        assert connection.execute(AVERAGES).fetchall() == []


@pytest.mark.parametrize("transaction_end", ["commit", "rollback"])
def test_context_does_not_leak_on_connection_reuse(company_actors, transaction_end):
    first, second = company_actors
    with database() as connection:
        set_actor(connection, first)
        assert connection.execute(AVERAGES).fetchall() == [first["expected"]]
        if transaction_end == "commit":
            connection.commit()
        else:
            connection.rollback()

        # A later request on the same physical connection must fail closed
        # until its own identity has been supplied.
        assert connection.execute(AVERAGES).fetchall() == []
        set_actor(connection, second)
        assert connection.execute(AVERAGES).fetchall() == [second["expected"]]


def test_connections_have_independent_context(company_actors):
    first, second = company_actors
    with database(first["account_id"]) as first_connection:
        with database(second["account_id"]) as second_connection:
            assert first_connection.execute(AVERAGES).fetchall() == [first["expected"]]
            assert second_connection.execute(AVERAGES).fetchall() == [second["expected"]]
            assert first_connection.execute(AVERAGES).fetchall() == [first["expected"]]


def test_membership_change_applies_without_changing_context(company_actors):
    actor, other = company_actors
    with database(actor["account_id"]) as connection:
        assert connection.execute(AVERAGES).fetchall() == [actor["expected"]]
        with admin_db() as administrator:
            administrator.execute("""UPDATE access_control.company_memberships
                SET registration_number=%s WHERE account_id=%s""",
                (other["expected"]["company_registration_number"], actor["account_id"]))
        # Under the application's default READ COMMITTED isolation, the next
        # statement sees the changed membership without a new login/context.
        assert connection.execute(AVERAGES).fetchall() == [other["expected"]]


def test_direct_sql_login_cannot_spoof_api_context(company_actors):
    with admin_db() as connection:
        employee = connection.execute("""SELECT employee_email FROM access_control.accounts
            WHERE db_role='db_employee_a' AND active""").fetchone()
        assert employee, "Initialize the protection workshop first"
        expected = connection.execute("""SELECT employee_email, salary_eur
            FROM private_db.employment_contract WHERE employee_email=%s""",
            (employee["employee_email"],)).fetchall()
        assert expected

    config = {**settings()["database"], "user": "db_employee_a", "password": "WorkshopDB!2026"}
    with psycopg.connect(**config, row_factory=dict_row) as connection:
        # Only the trusted privacy_api login may use app.account_id as identity.
        set_actor(connection, company_actors[1])
        assert connection.execute("SELECT employee_email, salary_eur FROM private_db.employment_contract").fetchall() == expected
