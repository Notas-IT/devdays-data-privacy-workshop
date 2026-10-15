DO $$ DECLARE role_name text; BEGIN
    FOREACH role_name IN ARRAY ARRAY['workshop_owner','privacy_control_owner','privacy_audit_owner',
        'privacy_api','db_employee_a','db_employee_b','db_hr_a','db_finance_a'] LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('CREATE ROLE %I', role_name);
        END IF;
        EXECUTE format('ALTER ROLE %I NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT', role_name);
    END LOOP;
END $$;
ALTER ROLE workshop_owner NOLOGIN;
ALTER ROLE privacy_control_owner NOLOGIN;
ALTER ROLE privacy_audit_owner NOLOGIN;
ALTER ROLE privacy_api LOGIN;
ALTER ROLE db_employee_a LOGIN PASSWORD 'WorkshopDB!2026';
ALTER ROLE db_employee_b LOGIN PASSWORD 'WorkshopDB!2026';
ALTER ROLE db_hr_a LOGIN PASSWORD 'WorkshopDB!2026';
ALTER ROLE db_finance_a LOGIN PASSWORD 'WorkshopDB!2026';

CREATE SCHEMA IF NOT EXISTS access_control AUTHORIZATION privacy_control_owner;
CREATE SCHEMA IF NOT EXISTS security_audit AUTHORIZATION privacy_audit_owner;
REVOKE ALL ON SCHEMA private_db, exercise, access_control, security_audit FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA private_db, exercise, access_control, security_audit FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

CREATE TABLE IF NOT EXISTS access_control.accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    db_role TEXT UNIQUE,
    person_id BIGINT REFERENCES private_db.person_identity(person_id),
    employee_email TEXT REFERENCES private_db.person_identity(email),
    employee_phone TEXT REFERENCES private_db.person_identity(phone),
    salary_scope TEXT NOT NULL DEFAULT 'none' CHECK (salary_scope IN ('none','self','company','all')),
    profit_scope TEXT NOT NULL DEFAULT 'none' CHECK (profit_scope IN ('none','company','all')),
    can_view_pii BOOLEAN NOT NULL DEFAULT FALSE,
    can_manage_users BOOLEAN NOT NULL DEFAULT FALSE,
    can_view_audit BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    policy_revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS access_control.company_memberships (
    account_id BIGINT REFERENCES access_control.accounts(account_id) ON DELETE CASCADE,
    registration_number TEXT REFERENCES private_db.company(registration_number),
    PRIMARY KEY (account_id, registration_number)
);
CREATE TABLE IF NOT EXISTS access_control.sessions (
    token_hash TEXT PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES access_control.accounts(account_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS access_control.login_limits (
    bucket TEXT PRIMARY KEY,
    window_start TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    failures INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS security_audit.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    request_id UUID NOT NULL UNIQUE,
    actor_id BIGINT,
    action TEXT NOT NULL,
    resource_kind TEXT,
    resource_id BIGINT,
    outcome TEXT NOT NULL CHECK (outcome IN ('allowed','denied','failed')),
    http_status INTEGER NOT NULL,
    policy_revision INTEGER,
    details JSONB NOT NULL DEFAULT '{}'
);
ALTER TABLE access_control.accounts OWNER TO privacy_control_owner;
ALTER TABLE access_control.company_memberships OWNER TO privacy_control_owner;
ALTER TABLE access_control.sessions OWNER TO privacy_control_owner;
ALTER TABLE access_control.login_limits OWNER TO privacy_control_owner;
ALTER TABLE security_audit.events OWNER TO privacy_audit_owner;

CREATE OR REPLACE FUNCTION access_control.actor_id() RETURNS BIGINT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT account_id FROM access_control.accounts WHERE active AND
      (db_role = session_user OR
       (session_user = 'privacy_api' AND account_id::text = current_setting('app.account_id', true)))
$$;
CREATE OR REPLACE FUNCTION access_control.person_id() RETURNS BIGINT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT person_id FROM access_control.accounts WHERE account_id = access_control.actor_id()
$$;
CREATE OR REPLACE FUNCTION access_control.email() RETURNS TEXT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT employee_email FROM access_control.accounts WHERE account_id = access_control.actor_id()
$$;
CREATE OR REPLACE FUNCTION access_control.phone() RETURNS TEXT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT employee_phone FROM access_control.accounts WHERE account_id = access_control.actor_id()
$$;
CREATE OR REPLACE FUNCTION access_control.scope(kind TEXT) RETURNS TEXT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT CASE WHEN kind='salary' THEN salary_scope WHEN kind='profit' THEN profit_scope ELSE 'none' END
    FROM access_control.accounts WHERE account_id = access_control.actor_id()
$$;
CREATE OR REPLACE FUNCTION access_control.companies() RETURNS TEXT[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT COALESCE(array_agg(registration_number), ARRAY[]::text[])
    FROM access_control.company_memberships WHERE account_id = access_control.actor_id()
$$;
DO $$ DECLARE f record; BEGIN
    FOR f IN SELECT p.oid::regprocedure AS signature FROM pg_proc p
      JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='access_control' LOOP
        EXECUTE format('ALTER FUNCTION %s OWNER TO privacy_control_owner', f.signature);
    END LOOP;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA access_control FROM PUBLIC;
GRANT USAGE ON SCHEMA access_control TO privacy_api, workshop_owner, db_employee_a, db_employee_b, db_hr_a, db_finance_a;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA access_control TO privacy_api, workshop_owner, db_employee_a, db_employee_b, db_hr_a, db_finance_a;

DO $$ DECLARE table_name text; BEGIN
    FOREACH table_name IN ARRAY ARRAY['person_identity','company','employment_contract','payroll_event','benefit_claim','application_user'] LOOP
        EXECUTE format('ALTER TABLE private_db.%I OWNER TO workshop_owner', table_name);
        EXECUTE format('ALTER TABLE private_db.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE private_db.%I NO FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS workshop_access ON private_db.%I', table_name);
    END LOOP;
END $$;
ALTER SCHEMA private_db OWNER TO workshop_owner;

CREATE POLICY workshop_access ON private_db.employment_contract FOR SELECT USING (
    (SELECT access_control.scope('salary')) = 'all' OR
    ((SELECT access_control.scope('salary')) = 'self' AND employee_email = (SELECT access_control.email())) OR
    ((SELECT access_control.scope('salary')) = 'company' AND
       company_registration_number = ANY((SELECT access_control.companies())::text[]))
);
CREATE POLICY workshop_access ON private_db.person_identity FOR SELECT USING (
    person_id = (SELECT access_control.person_id()) OR (SELECT access_control.scope('salary')) = 'all' OR
    ((SELECT access_control.scope('salary')) = 'company' AND EXISTS (
        SELECT FROM private_db.employment_contract e WHERE e.national_id = person_identity.national_id
          AND e.company_registration_number = ANY((SELECT access_control.companies())::text[])))
);
CREATE POLICY workshop_access ON private_db.company FOR SELECT USING (
    (SELECT access_control.scope('profit')) = 'all' OR
    ((SELECT access_control.scope('profit')) = 'company' AND
        registration_number = ANY((SELECT access_control.companies())::text[])) OR
    (session_user <> 'privacy_api' AND registration_number = ANY((SELECT access_control.companies())::text[]))
);
CREATE POLICY workshop_access ON private_db.payroll_event FOR SELECT USING (
    employee_email = (SELECT access_control.email())
);
CREATE POLICY workshop_access ON private_db.benefit_claim FOR SELECT USING (
    claimant_phone = (SELECT access_control.phone())
);
CREATE POLICY workshop_access ON private_db.application_user FOR SELECT USING (
    email = (SELECT access_control.email())
);
CREATE INDEX IF NOT EXISTS idx_protection_employment_email ON private_db.employment_contract(employee_email);
CREATE INDEX IF NOT EXISTS idx_protection_employment_company ON private_db.employment_contract(company_registration_number);

GRANT USAGE ON SCHEMA private_db TO privacy_api, db_employee_a, db_employee_b, db_hr_a, db_finance_a;
GRANT SELECT ON private_db.person_identity, private_db.employment_contract,
    private_db.payroll_event, private_db.benefit_claim, private_db.application_user
    TO db_employee_a, db_employee_b, db_hr_a;
GRANT SELECT (company_id, registration_number, company_name, industry, headquarters_city, employee_count)
    ON private_db.company TO db_employee_a, db_employee_b, db_hr_a;
GRANT SELECT ON private_db.company TO db_finance_a;
GRANT SELECT (person_id, national_id, first_name, last_name, email, phone)
    ON private_db.person_identity TO privacy_api;
GRANT SELECT (national_id, employee_email, company_registration_number, role_title, salary_eur, bonus_eur)
    ON private_db.employment_contract TO privacy_api;
GRANT SELECT (company_id, registration_number, company_name, annual_revenue_eur, annual_profit_eur)
    ON private_db.company TO privacy_api;
GRANT USAGE ON SCHEMA public_db TO privacy_api, db_employee_a, db_employee_b, db_hr_a, db_finance_a;
GRANT SELECT ON ALL TABLES IN SCHEMA public_db TO privacy_api, db_employee_a, db_employee_b, db_hr_a, db_finance_a;

GRANT SELECT, INSERT ON access_control.accounts TO privacy_api;
GRANT UPDATE (salary_scope, profit_scope, can_view_pii, can_manage_users, can_view_audit, active, policy_revision)
    ON access_control.accounts TO privacy_api;
GRANT SELECT, INSERT, DELETE ON access_control.company_memberships TO privacy_api;
GRANT SELECT, INSERT, UPDATE ON access_control.sessions TO privacy_api;
GRANT SELECT, INSERT, UPDATE ON access_control.login_limits TO privacy_api;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA access_control TO privacy_api;
GRANT USAGE ON SCHEMA security_audit TO privacy_api;
GRANT SELECT, INSERT ON security_audit.events TO privacy_api;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA security_audit TO privacy_api;
