"""Integration tests against the initialized synthetic workshop database."""

import os
import uuid

import psycopg
from psycopg.rows import dict_row
import pytest
from fastapi.testclient import TestClient

import app as api
from storage import database, private_hash, settings, token_hash

PASSWORD = "Workshop!2026"


def admin_db():
    return psycopg.connect(os.environ["ADMIN_DSN"], row_factory=dict_row)


@pytest.fixture
def client():
    with TestClient(api.app) as client:
        yield client


def login(client, username):
    response = client.post("/auth/token", data={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def temporary_user(client):
    username = "test_" + uuid.uuid4().hex[:12]
    administrator = headers(login(client, "admin"))
    permissions = {"salary_scope": "self", "profit_scope": "none", "company_ids": [],
                   "can_view_pii": True, "can_manage_users": False, "can_view_audit": False, "active": True}
    response = client.post("/admin/users", headers=administrator,
                           json={**permissions, "username": username, "password": PASSWORD,
                                 "person_id": settings()["demo"]["person_a"]})
    assert response.status_code == 201, response.text
    try:
        yield username, administrator, permissions
    finally:
        with admin_db() as connection:
            connection.execute("DELETE FROM access_control.accounts WHERE username=%s", (username,))
            connection.execute("DELETE FROM access_control.login_limits WHERE bucket=%s", (private_hash(username),))


def test_employee_cannot_impersonate_colleague(client):
    demo = settings()["demo"]
    employee = headers(login(client, "employee_a"))
    assert client.get("/people").status_code == 401
    assert client.get(f'/people/{demo["person_a"]}/salary', headers=employee).status_code == 200
    spoofed = {**employee, "X-User": "admin", "X-Account-ID": "5"}
    assert client.get(f'/people/{demo["colleague_a"]}/salary', headers=spoofed).status_code == 404
    assert client.get(f'/companies/{demo["company_a"]}/financials', headers=employee).status_code == 403
    assert client.get("/admin/users", headers=employee).status_code == 403
    assert client.get("/admin/audit", headers=employee).status_code == 403


def test_company_boundaries(client):
    demo = settings()["demo"]
    hr = headers(login(client, "hr_a"))
    assert client.get(f'/people/{demo["colleague_a"]}/salary', headers=hr).status_code == 200
    assert client.get(f'/people/{demo["person_b"]}/salary', headers=hr).status_code == 404
    finance = headers(login(client, "finance_a"))
    assert client.get(f'/companies/{demo["company_a"]}/financials', headers=finance).status_code == 200
    assert client.get(f'/companies/{demo["company_b"]}/financials', headers=finance).status_code == 404
    assert client.get("/people", headers=finance).status_code == 403


def test_policy_changes_apply_to_existing_session_and_redact_pii(client, temporary_user):
    username, administrator, permissions = temporary_user
    employee = headers(login(client, username))
    assert "email" in client.get("/people", headers=employee).json()["items"][0]
    changed = {**permissions, "can_view_pii": False}
    assert client.put(f"/admin/users/{username}/permissions", headers=administrator, json=changed).status_code == 200
    row = client.get("/people", headers=employee).json()["items"][0]
    assert not {"email", "first_name", "last_name", "phone", "national_id"} & row.keys()
    changed["salary_scope"] = "none"
    assert client.put(f"/admin/users/{username}/permissions", headers=administrator, json=changed).status_code == 200
    assert client.get("/people", headers=employee).status_code == 403
    changed["active"] = False
    assert client.put(f"/admin/users/{username}/permissions", headers=administrator, json=changed).status_code == 200
    assert client.get("/me", headers=employee).status_code == 401


def test_tokens_hashed_expired_tampered_and_revoked(client):
    token = login(client, "employee_a")
    with admin_db() as connection:
        assert connection.execute("SELECT 1 FROM access_control.sessions WHERE token_hash=%s", (token,)).fetchone() is None
        assert connection.execute("SELECT 1 FROM access_control.sessions WHERE token_hash=%s", (token_hash(token),)).fetchone()
        connection.execute("UPDATE access_control.sessions SET expires_at=clock_timestamp()-interval '1 second' WHERE token_hash=%s", (token_hash(token),))
    assert client.get("/me", headers=headers(token)).status_code == 401
    token = login(client, "employee_a")
    assert client.get("/me", headers=headers(token + "x")).status_code == 401
    assert client.post("/auth/logout", headers=headers(token)).status_code == 204
    assert client.get("/me", headers=headers(token)).status_code == 401


def test_validation_and_last_admin_guard(client):
    administrator = headers(login(client, "admin"))
    assert client.put("/admin/users/admin/permissions", headers=administrator,
                      json={"active": False}).status_code == 409
    assert client.put("/admin/users/admin/permissions", headers=administrator,
                      json={"salary_scope": "company", "company_ids": []}).status_code == 422
    assert client.get("/people?limit=101", headers=administrator).status_code == 422


def test_audit_records_outcomes_without_secrets(client):
    token = login(client, "employee_a")
    response = client.get("/people", headers=headers(token))
    denied = client.get("/admin/audit", headers=headers(token))
    with admin_db() as connection:
        rows = connection.execute("SELECT * FROM security_audit.events WHERE request_id=ANY(%s::uuid[])",
                                  ([response.headers["X-Request-ID"], denied.headers["X-Request-ID"]],)).fetchall()
    assert {row["outcome"] for row in rows} == {"allowed", "denied"}
    assert PASSWORD not in str(rows) and token not in str(rows)
    assert "salary_eur" not in str(rows) and "password_hash" not in str(rows)
    assert response.headers["Cache-Control"] == "no-store"


def test_audit_is_append_only_for_api_role():
    for statement in ["UPDATE security_audit.events SET action='tampered' WHERE false",
                      "DELETE FROM security_audit.events WHERE false", "TRUNCATE security_audit.events"]:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with database() as connection:
                connection.execute(statement)


def test_audit_failure_blocks_data_and_rolls_back_permissions(client, temporary_user, monkeypatch):
    username, administrator, permissions = temporary_user
    employee = headers(login(client, username))
    def unavailable(*args, **kwargs):
        raise RuntimeError("simulated audit outage")
    monkeypatch.setattr(api, "record_audit", unavailable)
    response = client.get("/people", headers=employee)
    assert response.status_code == 503 and "salary_eur" not in response.text
    response = client.put(f"/admin/users/{username}/permissions", headers=administrator,
                          json={**permissions, "salary_scope": "all"})
    assert response.status_code == 503
    with admin_db() as connection:
        row = connection.execute("SELECT salary_scope FROM access_control.accounts WHERE username=%s", (username,)).fetchone()
    assert row["salary_scope"] == "self"


def test_login_throttling(client):
    username = "missing_" + uuid.uuid4().hex
    try:
        for _ in range(5):
            assert client.post("/auth/token", data={"username": username, "password": "incorrect"}).status_code == 401
        assert client.post("/auth/token", data={"username": username, "password": "incorrect"}).status_code == 429
    finally:
        with admin_db() as connection:
            connection.execute("DELETE FROM access_control.login_limits WHERE bucket=%s", (private_hash(username),))


def test_runtime_role_is_not_owner_or_bypass():
    with database() as connection:
        role = connection.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        assert not role["rolsuper"] and not role["rolbypassrls"]
        assert connection.execute("SELECT count(*) AS n FROM private_db.employment_contract").fetchone()["n"] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("SET ROLE workshop_owner")
