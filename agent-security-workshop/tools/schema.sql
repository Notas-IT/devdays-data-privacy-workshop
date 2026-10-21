DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='lab_owner') THEN
        CREATE ROLE lab_owner NOLOGIN;
        CREATE ROLE lab_auth NOLOGIN;
        CREATE ROLE lab_summary NOLOGIN;
        CREATE ROLE gateway_reader LOGIN;
    END IF;
END $$;
ALTER ROLE gateway_reader NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE lab_auth NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOLOGIN;
ALTER ROLE lab_summary NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOLOGIN;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA IF NOT EXISTS lab_public AUTHORIZATION lab_owner;
CREATE SCHEMA IF NOT EXISTS lab_private AUTHORIZATION lab_owner;
CREATE SCHEMA IF NOT EXISTS lab_control AUTHORIZATION lab_owner;
CREATE SCHEMA IF NOT EXISTS lab_api AUTHORIZATION lab_owner;
CREATE SCHEMA IF NOT EXISTS lab_audit AUTHORIZATION lab_owner;
REVOKE ALL ON SCHEMA lab_private, lab_control, lab_api, lab_audit FROM PUBLIC;

CREATE TABLE IF NOT EXISTS lab_public.projects (
    project_id integer PRIMARY KEY,
    title text NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_private.employee_salaries (
    employee_id integer PRIMARY KEY,
    company_id integer NOT NULL,
    employee_name text NOT NULL,
    salary_eur integer NOT NULL,
    security_canary text
);
CREATE TABLE IF NOT EXISTS lab_control.credentials (
    token_hash text PRIMARY KEY,
    actor text NOT NULL,
    company_id integer NOT NULL,
    active boolean NOT NULL DEFAULT true,
    expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_audit.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    request_id uuid NOT NULL UNIQUE,
    actor text,
    action text NOT NULL,
    company_id integer,
    status integer NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('allowed', 'denied', 'failed'))
);
ALTER TABLE lab_public.projects OWNER TO lab_owner;
ALTER TABLE lab_private.employee_salaries OWNER TO lab_owner;
ALTER TABLE lab_control.credentials OWNER TO lab_owner;
ALTER TABLE lab_audit.events OWNER TO lab_owner;

CREATE OR REPLACE FUNCTION lab_api.authenticate(p_token text)
RETURNS TABLE(actor text, company_id integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT c.actor, c.company_id FROM lab_control.credentials c
    WHERE c.token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex')
      AND c.active AND c.expires_at > statement_timestamp()
$$;
ALTER FUNCTION lab_api.authenticate(text) OWNER TO lab_auth;
REVOKE ALL ON FUNCTION lab_api.authenticate(text) FROM PUBLIC;
GRANT USAGE ON SCHEMA lab_control TO lab_auth;
GRANT SELECT ON lab_control.credentials TO lab_auth;

ALTER TABLE lab_private.employee_salaries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS company_scope ON lab_private.employee_salaries;
CREATE POLICY company_scope ON lab_private.employee_salaries FOR SELECT TO lab_summary
    USING (company_id = nullif(current_setting('app.company_id', true), '')::integer);
GRANT USAGE ON SCHEMA lab_private, lab_api TO lab_summary;
GRANT SELECT (company_id, salary_eur) ON lab_private.employee_salaries TO lab_summary;
GRANT EXECUTE ON FUNCTION lab_api.authenticate(text) TO lab_summary;

CREATE OR REPLACE FUNCTION lab_api.salary_summary(p_token text, p_company_id integer)
RETURNS TABLE(company_id integer, employee_count bigint, average_salary_eur numeric)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE caller record;
BEGIN
    SELECT * INTO caller FROM lab_api.authenticate(p_token);
    IF NOT FOUND OR caller.company_id <> p_company_id THEN
        RETURN;
    END IF;
    -- Caller-controlled SQL settings are overwritten using the verified identity.
    PERFORM set_config('app.company_id', caller.company_id::text, true);
    RETURN QUERY SELECT e.company_id, count(*), avg(e.salary_eur)
        FROM lab_private.employee_salaries e
        GROUP BY e.company_id HAVING count(*) >= 3;
END $$;
ALTER FUNCTION lab_api.salary_summary(text, integer) OWNER TO lab_summary;
REVOKE ALL ON FUNCTION lab_api.salary_summary(text, integer) FROM PUBLIC;

GRANT USAGE ON SCHEMA lab_public, lab_api, lab_audit TO gateway_reader;
GRANT SELECT ON lab_public.projects TO gateway_reader;
GRANT EXECUTE ON FUNCTION lab_api.authenticate(text), lab_api.salary_summary(text, integer) TO gateway_reader;
GRANT INSERT ON lab_audit.events TO gateway_reader;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA lab_audit TO gateway_reader;
