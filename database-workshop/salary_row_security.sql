BEGIN;

-- The view owner must be subject to RLS; the setup superuser bypasses it.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'salary_summary_owner') THEN
        CREATE ROLE salary_summary_owner NOLOGIN;
    END IF;
END $$;
ALTER ROLE salary_summary_owner WITH NOLOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT;

GRANT USAGE ON SCHEMA private_db TO salary_summary_owner;
REVOKE ALL ON private_db.company, private_db.employment_contract FROM salary_summary_owner;
GRANT SELECT (company_id, registration_number, company_name)
    ON private_db.company TO salary_summary_owner;
GRANT SELECT (company_registration_number, salary_eur)
    ON private_db.employment_contract TO salary_summary_owner;

ALTER TABLE private_db.company ENABLE ROW LEVEL SECURITY;
ALTER TABLE private_db.company FORCE ROW LEVEL SECURITY;
-- Replace policies left by the earlier access-control workshop implementation.
DROP POLICY IF EXISTS workshop_access ON private_db.company;
DROP POLICY IF EXISTS company_session_select ON private_db.company;
CREATE POLICY company_session_select ON private_db.company
    FOR SELECT TO salary_summary_owner
    USING (company_id = nullif(current_setting('app.company_id', true), '')::bigint);

ALTER TABLE private_db.employment_contract ENABLE ROW LEVEL SECURITY;
ALTER TABLE private_db.employment_contract FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workshop_access ON private_db.employment_contract;
DROP POLICY IF EXISTS salary_company_session_select ON private_db.employment_contract;
CREATE POLICY salary_company_session_select ON private_db.employment_contract
    FOR SELECT TO salary_summary_owner
    USING (company_registration_number IN (
        SELECT registration_number FROM private_db.company
        WHERE company_id = nullif(current_setting('app.company_id', true), '')::bigint
    ));

GRANT CREATE ON SCHEMA private_db TO salary_summary_owner;
ALTER VIEW private_db.company_average_salary OWNER TO salary_summary_owner;
ALTER VIEW private_db.company_average_salary SET (security_invoker = false);
REVOKE CREATE ON SCHEMA private_db FROM salary_summary_owner;

-- salary_viewer keeps SELECT on the aggregate view only, not the raw tables.
COMMIT;
