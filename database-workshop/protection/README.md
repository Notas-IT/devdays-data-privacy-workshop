# Database Access Protection

This extends the existing synthetic dataset without regenerating or removing data.
It compares database-user restrictions with an authenticated API and makes the
remaining owner/administrator trust boundary visible.

## Run

Run from `database-workshop` (the same commands also work at repository root):

```bash
docker compose up -d postgres
docker compose build db-security-tools privacy-api
docker compose run --rm db-security-tools init
docker compose run --rm db-security-tools owner-demo
docker compose up -d privacy-api
docker compose run --rm db-security-tools api-demo
docker compose run --rm --entrypoint pytest db-security-tools -q
```

The original schema and dataset must already be loaded; see the parent README
for a fresh installation. `init` is repeatable but resets the demo accounts'
permissions/passwords and revokes their sessions. It does not reset the dataset.
After resetting the original schema, rerun `init` before using protection.

Interactive API documentation: http://localhost:18000/docs. Select **Authorize**
and enter a demo username/password. This workshop uses username/password login
and opaque bearer sessions, not an external identity provider.

## Database Users And The Owner Flaw

SQL logins use password `WorkshopDB!2026` on localhost:5432, database
`privacy_workshop`:

| Login | Restricted view |
| --- | --- |
| `db_employee_a`, `db_employee_b` | Own identity, salary, payroll, claims and application-user rows; assigned company's non-financial columns |
| `db_hr_a` | Assigned-company identities and salaries; only own payroll, claims and application-user rows |
| `db_finance_a` | Assigned-company financials |

Example (enter the SQL demo password at the prompt):

```bash
psql -h localhost -U db_employee_a -d privacy_workshop -W \
  -c 'SELECT count(*) FROM private_db.employment_contract;'
```

Row-level security binds direct SQL users to `session_user`; setting
`app.account_id` cannot impersonate another SQL user. Column grants separately
deny employees and HR access to company profit/revenue. No access is granted to
the reconstruction views, whose owner's privileges would otherwise bypass RLS.

`owner-demo` uses the privileged presenter connection to assume the NOLOGIN,
non-superuser, non-BYPASSRLS `workshop_owner` role:

1. Employee sees one salary; HR sees one company; finance sees one company.
2. Table owner sees all 100,000 salaries because owners normally bypass RLS.
3. `FORCE ROW LEVEL SECURITY` filters this unmapped owner to zero rows.
4. The owner can remove `FORCE` and read everything again.

The demonstration restores the intended non-forced workshop configuration.
RLS is not a security boundary against the table owner or a database superuser.

## API Permissions

All demo API accounts have synthetic password `Workshop!2026`:

| Username | Salary | Profit | Other permissions |
| --- | --- | --- | --- |
| `employee_a`, `employee_b` | Self | None | Names/email in permitted salary responses |
| `hr_a` | Assigned company | None | Names/email in permitted salary responses |
| `finance_a` | None | Assigned company | No personal details |
| `admin` | All | All | Personal details, user management, audit |
| `auditor` | None | None | Audit only |

```bash
TOKEN=$(curl -fsS http://localhost:18000/auth/token \
  -d 'username=employee_a&password=Workshop!2026' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -fsS http://localhost:18000/me -H "Authorization: Bearer $TOKEN"
curl -fsS http://localhost:18000/people -H "Authorization: Bearer $TOKEN"
docker compose run --rm db-security-tools demo-ids
```

Use the numeric IDs from `demo-ids` to request
`GET /people/{person_id}/salary` and
`GET /companies/{company_id}/financials`. Hidden and nonexistent resources both
return 404; entirely disallowed capabilities return 403. All lists are bounded.

Authenticate as `admin` to configure an existing account with
`PUT /admin/users/{username}/permissions`. This is a full permission replacement,
not a partial patch. Example body for HR without names/email:

```json
{
  "salary_scope": "company",
  "profit_scope": "none",
  "company_ids": [1],
  "can_view_pii": false,
  "can_manage_users": false,
  "can_view_audit": false,
  "active": true
}
```

Salary scopes are `none`, `self`, `company`, `all`; profit scopes are `none`,
`company`, `all`. Company scopes require valid company IDs. Changes apply on the
next request, including requests using an existing token. Disabling an account
revokes its sessions. Removing the last active permissions administrator is
rejected. Administrators can create accounts with `POST /admin/users`, adding
`username`, `password` (12+ characters) and optional `person_id` to this body.
Use `/admin/users` to inspect configured permissions, never password hashes.
The original generated `private_db.application_user` flags are exercise data,
not the API's authorization authority.

## Authentication And Audit

- Passwords use Argon2 hashes; unknown users use a dummy verification hash.
- Bearer tokens contain 32 random bytes, expire after 15 minutes, and only their
  SHA-256 hashes are stored. Logout revokes immediately. Five failed logins per
  normalized username in five minutes trigger throttling.
- API requests cannot choose actor IDs or SQL. A non-owner, non-superuser,
  non-BYPASSRLS database role supplies transaction-local actor context after
  authentication. RLS enforces row boundaries; explicit projections limit fields.
- Every non-public HTTP request records a server-generated request ID, actor,
  action, numeric resource ID, outcome, status and policy revision. Login,
  logout and permission changes commit with their audit record.
- Passwords, bearer tokens, raw request bodies, URLs/query strings, salaries and
  personal names are not written to audit events. Failed-login names use keyed
  hashes. Permission changes record permission metadata before/after.
- Failed audit writes block successful data delivery with 503; permission
  changes roll back. The API role can insert/read audit events, but cannot
  update, delete or truncate them. Audit/control objects have separate owners
  from private data tables. Use `GET /admin/audit` as admin or auditor.

## Security Boundary

This is a local workshop, **not a production deployment**. Ports bind to
localhost, published passwords are deliberately demo-only, and HTTP is used for
local simulation. Production needs TLS, unique credentials, an identity
provider/MFA where appropriate, secret management, network restrictions,
global/IP rate limits, session cleanup, monitoring and external durable audit
retention. No client should receive database-owner/admin credentials or the
API's randomly generated database credential in the private runtime volume.

The API is a trusted broker: its database credential can supply actor context
and manage accounts. RLS does not protect against compromise of that credential.
Likewise, direct owner/superuser SQL access bypasses API authorization and is
**not captured by API audit**. A privileged database administrator or audit
owner can alter local audit storage; use independent database auditing and an
external tamper-resistant sink for that threat model.

Access control also does not anonymize data: permitting public reference data
can still enable the reconstruction exercise from the parent workshop.

## Tests

The Docker pytest command runs integration tests against the initialized live
Postgres dataset, using the real restricted API database role. It covers
employee/company isolation, spoofed identity headers, PII projections,
immediate permission changes, token storage/expiry/tampering/revocation,
validation, last-admin protection, login throttling, safe audit contents,
append-only grants and audit-failure rollback. Temporary test accounts are
removed; synthetic audit records remain. Run tests serially, not alongside an
`init` or a live permissions-editing demonstration.

### Testing Request Context And RLS

Run only the database session-context tests:

```bash
docker compose build db-security-tools
docker compose run --rm --entrypoint pytest db-security-tools -q test_rls_session.py
```

`test_rls_session.py` creates temporary accounts for two companies from the
loaded dataset. It calculates expected averages using the administrator, then
runs the same aggregate query without a company filter as the restricted
`privacy_api` role. Account IDs, company registrations, employee counts and
expected averages come from fixtures rather than hardcoded company data.

The application passes the authenticated account into each transaction:

```python
with database(account_id) as connection:
    rows = connection.execute("""
        SELECT company_registration_number, AVG(salary_eur)
        FROM private_db.employment_contract
        GROUP BY company_registration_number
    """).fetchall()
```

`database(account_id)` binds the value using
`SELECT set_config('app.account_id', %s, true)`. RLS resolves the account's
current permissions and company memberships. The `true` makes this context
transaction-local, so a commit or rollback clears it before connection reuse.
A session-wide setting (`false`) would persist after commit and require an
explicit reset. See PostgreSQL's [configuration settings functions](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADMIN-SET).

These are integration tests against real PostgreSQL policies. They check both
company averages, absent/invalid context, inactive accounts, removed membership,
denied salary permission, context isolation between connections, cleanup after
commit/rollback, live membership changes and SQL-user impersonation attempts.
Temporary accounts and their memberships are removed afterward.

The API login is trusted to set account context after authentication; custom
settings are not proof of identity for an untrusted SQL client. Direct SQL
logins remain bound to `session_user`. These tests verify company isolation
while calculating averages; the existing API role also has row-level salary
access. An averages-only interface additionally needs a restricted aggregate
view or function, as RLS itself does not restrict which aggregates may be run.
