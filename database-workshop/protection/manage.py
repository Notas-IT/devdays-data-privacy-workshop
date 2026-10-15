"""Privileged setup and local demonstrations; never used by the running API."""

import argparse
import json
import os
from pathlib import Path
import secrets

import httpx
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from pwdlib import PasswordHash

from storage import RUNTIME

DEMO_PASSWORD = "Workshop!2026"
DB_PASSWORD = "WorkshopDB!2026"


def administrator():
    return psycopg.connect(os.environ["ADMIN_DSN"], row_factory=dict_row)


def initialize():
    runtime_path = RUNTIME / "connection.json"
    if runtime_path.exists():
        runtime = json.loads(runtime_path.read_text())
    else:
        runtime = {"database": {"host": "postgres", "port": 5432, "dbname": "privacy_workshop",
                    "user": "privacy_api", "password": secrets.token_urlsafe(32)},
                   "audit_pepper": secrets.token_hex(32)}
    with administrator() as connection:
        company_ids = connection.execute("SELECT company_id,registration_number FROM private_db.company ORDER BY company_id LIMIT 2").fetchall()
        if len(company_ids) != 2:
            raise RuntimeError("Generate and load at least two companies first")
        people = []
        for company in company_ids:
            rows = connection.execute("""SELECT p.person_id,p.email,p.phone FROM private_db.person_identity p
                JOIN private_db.employment_contract e USING(national_id)
                WHERE e.company_registration_number=%s ORDER BY p.person_id LIMIT 3""", (company["registration_number"],)).fetchall()
            if len(rows) < 2:
                raise RuntimeError("This protection example needs at least two people in each demo company")
            people.append(rows)
        connection.execute((Path(__file__).parent / "sql" / "security.sql").read_text())
        connection.execute(sql.SQL("ALTER ROLE privacy_api PASSWORD {}").format(sql.Literal(runtime["database"]["password"])))
        profiles = [
            ("employee_a", "db_employee_a", people[0][0], "self", "none", True, False, False, [company_ids[0]]),
            ("employee_b", "db_employee_b", people[1][0], "self", "none", True, False, False, [company_ids[1]]),
            ("hr_a", "db_hr_a", people[0][1], "company", "none", True, False, False, [company_ids[0]]),
            ("finance_a", "db_finance_a", people[0][-1], "none", "company", False, False, False, [company_ids[0]]),
            ("admin", None, None, "all", "all", True, True, True, []),
            ("auditor", None, None, "none", "none", False, False, True, []),
        ]
        hasher = PasswordHash.recommended()
        for username, role, person, salary, profit, pii, manage, audit, companies in profiles:
            person = person or {"person_id": None, "email": None, "phone": None}
            account_id = connection.execute("""INSERT INTO access_control.accounts
                (username,password_hash,db_role,person_id,employee_email,employee_phone,salary_scope,profit_scope,
                 can_view_pii,can_manage_users,can_view_audit)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(username) DO UPDATE SET password_hash=EXCLUDED.password_hash,db_role=EXCLUDED.db_role,
                person_id=EXCLUDED.person_id,employee_email=EXCLUDED.employee_email,employee_phone=EXCLUDED.employee_phone,
                salary_scope=EXCLUDED.salary_scope,profit_scope=EXCLUDED.profit_scope,can_view_pii=EXCLUDED.can_view_pii,
                can_manage_users=EXCLUDED.can_manage_users,can_view_audit=EXCLUDED.can_view_audit,active=true,
                policy_revision=access_control.accounts.policy_revision+1 RETURNING account_id""",
                (username, hasher.hash(DEMO_PASSWORD), role, person["person_id"], person["email"], person["phone"],
                 salary, profit, pii, manage, audit)).fetchone()["account_id"]
            connection.execute("DELETE FROM access_control.company_memberships WHERE account_id=%s", (account_id,))
            for company in companies:
                connection.execute("INSERT INTO access_control.company_memberships VALUES (%s,%s)", (account_id, company["registration_number"]))
            connection.execute("UPDATE access_control.sessions SET revoked=true WHERE account_id=%s", (account_id,))
        runtime["demo"] = {"person_a": people[0][0]["person_id"], "colleague_a": people[0][1]["person_id"],
                           "person_b": people[1][0]["person_id"], "company_a": company_ids[0]["company_id"],
                           "company_b": company_ids[1]["company_id"]}
    RUNTIME.mkdir(parents=True, exist_ok=True)
    temporary = runtime_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(runtime), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(runtime_path)
    print("Protection initialized without changing the 100k person dataset")
    print("API users: employee_a, employee_b, hr_a, finance_a, admin, auditor")
    print(f"Synthetic API password for all demo users: {DEMO_PASSWORD}")
    print(json.dumps(runtime["demo"]))


def database_role(role):
    return psycopg.connect(host="postgres", dbname="privacy_workshop", user=role, password=DB_PASSWORD, row_factory=dict_row)


def owner_demo():
    with database_role("db_employee_a") as employee:
        count = employee.execute("SELECT count(*) AS count FROM private_db.employment_contract").fetchone()["count"]
        assert count == 1
        employee.execute("SELECT set_config('app.account_id','999999',false)")
        assert employee.execute("SELECT count(*) AS count FROM private_db.employment_contract").fetchone()["count"] == 1
        print("PASS: employee sees one salary row; client-set identity context cannot impersonate another DB user")
    with database_role("db_hr_a") as hr:
        count = hr.execute("SELECT count(*) AS count FROM private_db.employment_contract").fetchone()["count"]
        print(f"PASS: HR sees only assigned-company salaries ({count} rows)")
    with database_role("db_finance_a") as finance:
        assert finance.execute("SELECT count(*) AS count FROM private_db.company").fetchone()["count"] == 1
        print("PASS: finance sees one assigned company's financials")
    with administrator() as owner:
        owner.execute("SET LOCAL ROLE workshop_owner")
        flags = owner.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        assert not flags["rolsuper"] and not flags["rolbypassrls"]
        all_rows = owner.execute("SELECT count(*) AS count FROM private_db.employment_contract").fetchone()["count"]
        assert all_rows > count
        print(f"OWNER BYPASS: non-superuser table owner sees every salary ({all_rows} rows)")
        owner.execute("ALTER TABLE private_db.employment_contract FORCE ROW LEVEL SECURITY")
        assert owner.execute("SELECT count(*) AS count FROM private_db.employment_contract").fetchone()["count"] == 0
        print("FORCE RLS: unmapped owner is filtered to zero rows")
        owner.execute("ALTER TABLE private_db.employment_contract NO FORCE ROW LEVEL SECURITY")
        assert owner.execute("SELECT count(*) AS count FROM private_db.employment_contract").fetchone()["count"] == all_rows
        print("OWNER CONTROL: owner can remove FORCE and inspect all rows again")


def api_demo():
    runtime = json.loads((RUNTIME / "connection.json").read_text())
    demo = runtime["demo"]
    with httpx.Client(base_url=os.environ.get("API_URL", "http://privacy-api:8000"), timeout=20) as client:
        def login(username):
            response = client.post("/auth/token", data={"username": username, "password": DEMO_PASSWORD})
            response.raise_for_status()
            return {"Authorization": "Bearer " + response.json()["access_token"]}

        employee = login("employee_a")
        assert client.get(f"/people/{demo['person_a']}/salary").status_code == 401
        assert client.get(f"/people/{demo['person_a']}/salary", headers=employee).status_code == 200
        assert client.get(f"/people/{demo['colleague_a']}/salary", headers=employee).status_code == 404
        assert client.get(f"/companies/{demo['company_a']}/financials", headers=employee).status_code == 403
        assert client.get("/admin/audit", headers=employee).status_code == 403
        print("PASS: authenticated employee sees own salary and cannot inspect colleagues, profits, or audit logs")
        hr = login("hr_a")
        assert client.get(f"/people/{demo['colleague_a']}/salary", headers=hr).status_code == 200
        assert client.get(f"/people/{demo['person_b']}/salary", headers=hr).status_code == 404
        finance = login("finance_a")
        assert client.get(f"/companies/{demo['company_a']}/financials", headers=finance).status_code == 200
        assert client.get(f"/companies/{demo['company_b']}/financials", headers=finance).status_code == 404
        print("PASS: HR and finance are bounded to assigned companies")
        admin = login("admin")
        audit = client.get("/admin/audit", headers=admin)
        audit.raise_for_status()
        events = audit.json()["items"]
        assert any(event["outcome"] == "denied" for event in events)
        assert any(event["outcome"] == "allowed" for event in events)
        serialized = json.dumps(events)
        assert DEMO_PASSWORD not in serialized and employee["Authorization"] not in serialized
        print("PASS: audit records allowed and denied actions without passwords, bearer tokens, salaries, or response bodies")
        assert client.post("/auth/logout", headers=employee).status_code == 204
        assert client.get("/me", headers=employee).status_code == 401
        print("PASS: logout immediately revokes the opaque bearer token")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "owner-demo", "api-demo", "demo-ids"])
    args = parser.parse_args()
    if args.command == "init":
        initialize()
    elif args.command == "owner-demo":
        owner_demo()
    elif args.command == "api-demo":
        api_demo()
    elif args.command == "demo-ids":
        print(json.dumps(json.loads((RUNTIME / "connection.json").read_text())["demo"]))


if __name__ == "__main__":
    main()
