"""Authenticated, scoped data access with durable audit logging."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import secrets
import uuid

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import psycopg
from pwdlib import PasswordHash

from models import NewUser, Permissions
from storage import database, private_hash, record_audit, token_hash

PASSWORDS = PasswordHash.recommended()
DUMMY_HASH = PASSWORDS.hash("unused-dummy-password")
BEARER = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)
PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
ACCOUNT_COLUMNS = "account_id, username, person_id, salary_scope, profit_scope, can_view_pii, can_manage_users, can_view_audit, active, policy_revision"


@asynccontextmanager
async def lifespan(_):
    with database() as connection:
        role = connection.execute("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        if role["rolname"] != "privacy_api" or role["rolsuper"] or role["rolbypassrls"]:
            raise RuntimeError("API must use its non-owner, non-superuser, non-BYPASSRLS role")
        unsafe = connection.execute("""SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='private_db' AND c.relkind IN ('r','p')
              AND (c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)
                   OR NOT c.relrowsecurity) LIMIT 1""").fetchone()
        if unsafe:
            raise RuntimeError("Private tables must enable RLS and have a different owner")
        connection.execute("SELECT 1 FROM access_control.accounts LIMIT 1")
    yield


app = FastAPI(title="Database Privacy Workshop API", version="1.0.0", lifespan=lifespan)


def target(request, action, kind=None, identifier=None):
    request.state.action = action
    request.state.resource_kind = kind
    request.state.resource_id = identifier


@app.middleware("http")
async def audit_requests(request: Request, call_next):
    request.state.request_id = uuid.uuid4()
    request.state.actor = None
    request.state.audit_written = False
    target(request, "request")
    try:
        response = await call_next(request)
    except Exception:
        response = JSONResponse({"detail": "Request failed"}, status_code=503)
    if request.url.path not in PUBLIC_PATHS and not request.state.audit_written:
        if request.state.action in {"request", "authenticate"}:
            route = request.scope.get("route")
            request.state.action = "request_" + (getattr(route, "name", "unmatched") or "unmatched")
        # The response has not left this middleware: failed audit means no data delivery.
        try:
            with database() as connection:
                record_audit(connection, request, response.status_code)
        except Exception:
            if hasattr(response, "body_iterator") and hasattr(response.body_iterator, "aclose"):
                await response.body_iterator.aclose()
            response = JSONResponse({"detail": "Audit storage unavailable; request not delivered"}, status_code=503)
    response.headers["X-Request-ID"] = str(request.state.request_id)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(psycopg.Error)
async def database_error(_, error):
    # Driver error detail can contain sensitive row values; never echo or print it.
    return JSONResponse({"detail": "Database operation unavailable"}, status_code=503)


def authenticated(request: Request, bearer: str | None = Depends(BEARER)):
    target(request, "authenticate")
    if not bearer or len(bearer) > 512:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    with database() as connection:
        account = connection.execute("""SELECT a.*, s.token_hash FROM access_control.sessions s
            JOIN access_control.accounts a USING(account_id)
            WHERE s.token_hash=%s AND NOT s.revoked AND s.expires_at>clock_timestamp() AND a.active""",
            (token_hash(bearer),)).fetchone()
    if not account:
        raise HTTPException(401, "Invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"})
    request.state.actor = account
    return account


def require(account, capability):
    if not account[capability]:
        raise HTTPException(403, "Permission denied")


def public_account(connection, account_id):
    account = connection.execute(f"SELECT {ACCOUNT_COLUMNS} FROM access_control.accounts WHERE account_id=%s", (account_id,)).fetchone()
    memberships = connection.execute("""SELECT c.registry_id FROM access_control.company_memberships m
        JOIN public_db.company_registry c USING(registration_number) WHERE m.account_id=%s ORDER BY c.registry_id""", (account_id,)).fetchall()
    account["company_ids"] = [row["registry_id"] for row in memberships]
    return account


def registrations(connection, company_ids):
    rows = connection.execute("SELECT registry_id,registration_number FROM public_db.company_registry WHERE registry_id=ANY(%s)", (company_ids,)).fetchall()
    if len(rows) != len(company_ids):
        raise HTTPException(422, "Unknown company ID")
    return [row["registration_number"] for row in rows]


def apply_permissions(connection, account_id, permissions):
    values = permissions.model_dump()
    company_ids = values.pop("company_ids")
    scope = registrations(connection, company_ids)
    connection.execute("""UPDATE access_control.accounts SET
        salary_scope=%s,profit_scope=%s,can_view_pii=%s,can_manage_users=%s,can_view_audit=%s,
        active=%s,policy_revision=policy_revision+1 WHERE account_id=%s""",
        (values["salary_scope"], values["profit_scope"], values["can_view_pii"], values["can_manage_users"],
         values["can_view_audit"], values["active"], account_id))
    connection.execute("DELETE FROM access_control.company_memberships WHERE account_id=%s", (account_id,))
    for registration in scope:
        connection.execute("INSERT INTO access_control.company_memberships VALUES (%s,%s)", (account_id, registration))
    if not values["active"]:
        connection.execute("UPDATE access_control.sessions SET revoked=true WHERE account_id=%s", (account_id,))


@app.get("/health")
def health():
    with database() as connection:
        connection.execute("SELECT 1")
    return {"status": "ok"}


@app.post("/auth/token")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends()):
    target(request, "login", "account")
    if len(form.username) > 128 or len(form.password) > 128:
        raise HTTPException(401, "Invalid credentials")
    username = form.username.lower()
    bucket = private_hash(username)
    failure = None
    access_token = None
    with database() as connection:
        connection.execute("INSERT INTO access_control.login_limits(bucket) VALUES (%s) ON CONFLICT DO NOTHING", (bucket,))
        limit = connection.execute("SELECT * FROM access_control.login_limits WHERE bucket=%s FOR UPDATE", (bucket,)).fetchone()
        now = datetime.now(timezone.utc)
        if limit["window_start"] < now - timedelta(minutes=5):
            connection.execute("UPDATE access_control.login_limits SET failures=0,window_start=clock_timestamp() WHERE bucket=%s", (bucket,))
            limit["failures"] = 0
        if limit["failures"] >= 5:
            failure = 429
        else:
            account = connection.execute("SELECT * FROM access_control.accounts WHERE username=%s", (username,)).fetchone()
            verified = PASSWORDS.verify(form.password, account["password_hash"] if account else DUMMY_HASH)
            if not account or not verified or not account["active"]:
                connection.execute("UPDATE access_control.login_limits SET failures=failures+1 WHERE bucket=%s", (bucket,))
                failure = 401
            else:
                request.state.actor = account
                request.state.resource_id = account["account_id"]
                connection.execute("UPDATE access_control.login_limits SET failures=0 WHERE bucket=%s", (bucket,))
                access_token = secrets.token_urlsafe(32)
                connection.execute("""INSERT INTO access_control.sessions(token_hash,account_id,expires_at)
                    VALUES (%s,%s,clock_timestamp()+interval '15 minutes')""", (token_hash(access_token), account["account_id"]))
        record_audit(connection, request, failure or 200, details={"login_name_hash": bucket})
    request.state.audit_written = True
    if failure:
        raise HTTPException(failure, "Login temporarily limited" if failure == 429 else "Invalid credentials",
                            headers={"Retry-After": "300"} if failure == 429 else {"WWW-Authenticate": "Bearer"})
    return {"access_token": access_token, "token_type": "bearer", "expires_in": 900}


@app.post("/auth/logout", status_code=204)
def logout(request: Request, account=Depends(authenticated)):
    target(request, "logout", "account", account["account_id"])
    with database(account["account_id"]) as connection:
        connection.execute("UPDATE access_control.sessions SET revoked=true WHERE token_hash=%s", (account["token_hash"],))
        record_audit(connection, request, 204)
    request.state.audit_written = True


@app.get("/me")
def me(request: Request, account=Depends(authenticated)):
    target(request, "read_permissions", "account", account["account_id"])
    with database(account["account_id"]) as connection:
        # Membership IDs come from public registry; employees need no profit-table access.
        data = {key: account[key] for key in ACCOUNT_COLUMNS.split(", ")}
        rows = connection.execute("""SELECT c.registry_id FROM access_control.company_memberships m
            JOIN public_db.company_registry c USING(registration_number) WHERE m.account_id=%s ORDER BY c.registry_id""", (account["account_id"],)).fetchall()
        data["company_ids"] = [row["registry_id"] for row in rows]
    return data


def salary_rows(connection, account, person_id=None, limit=20, offset=0):
    if account["salary_scope"] == "none":
        raise HTTPException(403, "Salary access is not permitted")
    fields = "p.person_id,e.salary_eur,e.bonus_eur,e.role_title,e.company_registration_number"
    if account["can_view_pii"]:
        fields += ",p.first_name,p.last_name,p.email"
    clause = "WHERE p.person_id=%s" if person_id is not None else ""
    parameters = (person_id, limit, offset) if person_id is not None else (limit, offset)
    return connection.execute(f"""SELECT {fields} FROM private_db.person_identity p
        JOIN private_db.employment_contract e ON e.national_id=p.national_id
        {clause} ORDER BY p.person_id LIMIT %s OFFSET %s""", parameters).fetchall()


@app.get("/people")
def people(request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), account=Depends(authenticated)):
    target(request, "list_salaries", "person")
    with database(account["account_id"]) as connection:
        return {"items": salary_rows(connection, account, limit=limit, offset=offset)}


@app.get("/people/{person_id}/salary")
def salary(request: Request, person_id: int = Path(gt=0), account=Depends(authenticated)):
    target(request, "read_salary", "person", person_id)
    with database(account["account_id"]) as connection:
        rows = salary_rows(connection, account, person_id)
    if not rows:
        raise HTTPException(404, "Resource not available")
    return rows[0]


@app.get("/companies/{company_id}/financials")
def financials(request: Request, company_id: int = Path(gt=0), account=Depends(authenticated)):
    target(request, "read_financials", "company", company_id)
    if account["profit_scope"] == "none":
        raise HTTPException(403, "Company financial access is not permitted")
    with database(account["account_id"]) as connection:
        result = connection.execute("""SELECT company_id,company_name,annual_revenue_eur,annual_profit_eur
            FROM private_db.company WHERE company_id=%s""", (company_id,)).fetchone()
    if not result:
        raise HTTPException(404, "Resource not available")
    return result


@app.get("/admin/users")
def users(request: Request, account=Depends(authenticated)):
    target(request, "list_users", "account")
    require(account, "can_manage_users")
    with database(account["account_id"]) as connection:
        ids = connection.execute("SELECT account_id FROM access_control.accounts ORDER BY account_id LIMIT 100").fetchall()
        return {"items": [public_account(connection, item["account_id"]) for item in ids]}


@app.post("/admin/users", status_code=201)
def create_user(request: Request, body: NewUser, account=Depends(authenticated)):
    target(request, "create_user", "account")
    require(account, "can_manage_users")
    with database(account["account_id"]) as connection:
        if connection.execute("SELECT 1 FROM access_control.accounts WHERE username=%s", (body.username,)).fetchone():
            raise HTTPException(409, "Username is already configured")
        person = {"email": None, "phone": None}
        if body.person_id is not None:
            if account["salary_scope"] != "all":
                raise HTTPException(403, "Assigning an identity requires all-person management access")
            person = connection.execute("SELECT email,phone FROM private_db.person_identity WHERE person_id=%s", (body.person_id,)).fetchone()
            if not person:
                raise HTTPException(422, "Unknown person ID")
        created = connection.execute("""INSERT INTO access_control.accounts(username,password_hash,person_id,employee_email,employee_phone)
            VALUES (%s,%s,%s,%s,%s) RETURNING account_id""",
            (body.username, PASSWORDS.hash(body.password.get_secret_value()), body.person_id, person["email"], person["phone"])).fetchone()["account_id"]
        permissions = Permissions(**body.model_dump(exclude={"username", "password", "person_id"}))
        apply_permissions(connection, created, permissions)
        request.state.resource_id = created
        result = public_account(connection, created)
        record_audit(connection, request, 201, details={"after": permissions.model_dump()})
    request.state.audit_written = True
    return result


@app.put("/admin/users/{username}/permissions")
def permissions(request: Request, username: str, body: Permissions, account=Depends(authenticated)):
    target(request, "change_permissions", "account")
    require(account, "can_manage_users")
    with database(account["account_id"]) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(901772)")
        selected = connection.execute("SELECT * FROM access_control.accounts WHERE username=%s FOR UPDATE", (username,)).fetchone()
        if not selected:
            raise HTTPException(404, "Account not available")
        if selected["active"] and selected["can_manage_users"] and not (body.active and body.can_manage_users):
            count = connection.execute("SELECT count(*) AS count FROM access_control.accounts WHERE active AND can_manage_users").fetchone()["count"]
            if count <= 1:
                raise HTTPException(409, "At least one active permissions administrator is required")
        request.state.resource_id = selected["account_id"]
        before = public_account(connection, selected["account_id"])
        apply_permissions(connection, selected["account_id"], body)
        result = public_account(connection, selected["account_id"])
        before = {key: before[key] for key in Permissions.model_fields}
        record_audit(connection, request, 200, details={"before": before, "after": body.model_dump()})
    request.state.audit_written = True
    return result


@app.get("/admin/audit")
def audit(request: Request, limit: int = Query(50, ge=1, le=100), account=Depends(authenticated)):
    target(request, "read_audit", "audit")
    require(account, "can_view_audit")
    with database(account["account_id"]) as connection:
        rows = connection.execute("SELECT * FROM security_audit.events ORDER BY event_id DESC LIMIT %s", (limit,)).fetchall()
    return {"items": rows}
