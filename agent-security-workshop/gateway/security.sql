-- Aggregate access bound to a verified, active, unexpired token.
DO $$
DECLARE parent_role text;
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gateway_reader') THEN
        CREATE ROLE gateway_reader LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'layer_row_reader') THEN
        CREATE ROLE layer_row_reader NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lab_summary') THEN
        CREATE ROLE lab_summary NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lab_auth') THEN
        CREATE ROLE lab_auth NOLOGIN;
    END IF;
    -- NOINHERIT alone does not prevent SET ROLE. Remove existing memberships.
    FOR parent_role IN
        SELECT parent.rolname FROM pg_auth_members AS member
        JOIN pg_roles AS parent ON parent.oid = member.roleid
        WHERE member.member IN ('gateway_reader'::regrole, 'layer_row_reader'::regrole,
                                'lab_summary'::regrole, 'lab_auth'::regrole)
    LOOP
        EXECUTE format('REVOKE %I FROM gateway_reader, layer_row_reader, lab_summary, lab_auth', parent_role);
    END LOOP;
END $$;

ALTER ROLE gateway_reader WITH LOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT;
ALTER ROLE layer_row_reader WITH NOLOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT;
ALTER ROLE lab_summary WITH NOLOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT;
ALTER ROLE lab_auth WITH NOLOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT;

CREATE SCHEMA IF NOT EXISTS lab_api;
CREATE SCHEMA IF NOT EXISTS lab_control;
REVOKE ALL ON SCHEMA lab_control FROM PUBLIC, gateway_reader, lab_summary;
CREATE TABLE IF NOT EXISTS lab_control.credentials (
    token_hash text PRIMARY KEY,
    actor text NOT NULL,
    company_id integer NOT NULL,
    active boolean NOT NULL DEFAULT true,
    expires_at timestamptz NOT NULL
);
REVOKE ALL ON lab_control.credentials FROM PUBLIC, gateway_reader, lab_summary;
GRANT USAGE ON SCHEMA lab_control TO lab_auth;
GRANT SELECT ON lab_control.credentials TO lab_auth;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA lab_private, lab_api FROM PUBLIC;
REVOKE ALL ON SCHEMA lab_private FROM gateway_reader;
REVOKE ALL ON SCHEMA lab_api, lab_public FROM gateway_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA lab_public FROM gateway_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA lab_private FROM PUBLIC, gateway_reader;
REVOKE ALL (employee_id, company_id, employee_name, salary_eur, security_canary)
    ON lab_private.employee_salaries FROM PUBLIC, gateway_reader, layer_row_reader;
REVOKE ALL ON lab_private.employee_salaries FROM layer_row_reader;

GRANT USAGE ON SCHEMA lab_private, lab_api TO layer_row_reader;
GRANT SELECT (employee_id, company_id, employee_name, salary_eur)
    ON lab_private.employee_salaries TO layer_row_reader;
ALTER TABLE lab_private.employee_salaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE lab_private.employee_salaries FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS layer_direct ON lab_private.employee_salaries;
DROP POLICY IF EXISTS layer_rows ON lab_private.employee_salaries;
CREATE POLICY layer_rows ON lab_private.employee_salaries
    FOR SELECT TO layer_row_reader
    USING (company_id = nullif(current_setting('app.company_id', true), '')::integer);

CREATE OR REPLACE FUNCTION lab_api.salary_rows(p_company_id integer)
RETURNS TABLE(employee_id integer, company_id integer, employee_name text, salary_eur integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM set_config('app.company_id', p_company_id::text, true);
    RETURN QUERY SELECT e.employee_id, e.company_id, e.employee_name, e.salary_eur
        FROM lab_private.employee_salaries AS e;
END $$;
GRANT CREATE ON SCHEMA lab_api TO layer_row_reader;
ALTER FUNCTION lab_api.salary_rows(integer) OWNER TO layer_row_reader;
REVOKE CREATE ON SCHEMA lab_api FROM layer_row_reader;

-- The summary owner can read only the two columns needed for aggregation.
REVOKE ALL ON lab_private.employee_salaries FROM lab_summary;
REVOKE ALL (employee_id, company_id, employee_name, salary_eur, security_canary)
    ON lab_private.employee_salaries FROM lab_summary;
GRANT USAGE ON SCHEMA lab_private, lab_api TO lab_summary;
GRANT SELECT (company_id, salary_eur) ON lab_private.employee_salaries TO lab_summary;
DROP POLICY IF EXISTS layer_summary ON lab_private.employee_salaries;
CREATE POLICY layer_summary ON lab_private.employee_salaries
    FOR SELECT TO lab_summary
    USING (company_id = nullif(current_setting('app.company_id', true), '')::integer);

CREATE OR REPLACE FUNCTION lab_api.open_salary_summary(p_company_id integer)
RETURNS TABLE(company_id integer, employee_count bigint, average_salary_eur numeric)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM set_config('app.company_id', p_company_id::text, true);
    RETURN QUERY SELECT e.company_id, count(*), avg(e.salary_eur)
        FROM lab_private.employee_salaries AS e
        GROUP BY e.company_id;
END $$;
GRANT CREATE ON SCHEMA lab_api TO lab_summary;
ALTER FUNCTION lab_api.open_salary_summary(integer) OWNER TO lab_summary;
REVOKE CREATE ON SCHEMA lab_api FROM lab_summary;

CREATE OR REPLACE FUNCTION lab_api.authenticate(p_token text)
RETURNS TABLE(actor text, company_id integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT c.actor, c.company_id FROM lab_control.credentials AS c
    WHERE c.token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex')
      AND c.active AND c.expires_at > statement_timestamp()
$$;
GRANT USAGE, CREATE ON SCHEMA lab_api TO lab_auth;
ALTER FUNCTION lab_api.authenticate(text) OWNER TO lab_auth;
REVOKE CREATE ON SCHEMA lab_api FROM lab_auth;

CREATE OR REPLACE FUNCTION lab_api.salary_summary(p_token text, p_company_id integer)
RETURNS TABLE(company_id integer, employee_count bigint, average_salary_eur numeric)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE caller record;
BEGIN
    SELECT * INTO caller FROM lab_api.authenticate(p_token);
    IF NOT FOUND OR caller.company_id IS DISTINCT FROM p_company_id THEN
        RETURN;
    END IF;
    -- A caller-supplied GUC or identity header cannot override verified membership.
    PERFORM set_config('app.company_id', caller.company_id::text, true);
    RETURN QUERY SELECT e.company_id, count(*), avg(e.salary_eur)
        FROM lab_private.employee_salaries AS e
        GROUP BY e.company_id;
END $$;
GRANT CREATE ON SCHEMA lab_api TO lab_summary;
ALTER FUNCTION lab_api.salary_summary(text, integer) OWNER TO lab_summary;
REVOKE CREATE ON SCHEMA lab_api FROM lab_summary;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA lab_api FROM PUBLIC, gateway_reader;
GRANT USAGE ON SCHEMA lab_api, lab_public TO gateway_reader;
GRANT SELECT ON lab_public.projects TO gateway_reader;
GRANT EXECUTE ON FUNCTION lab_api.authenticate(text) TO lab_summary;
GRANT EXECUTE ON FUNCTION lab_api.authenticate(text),
    lab_api.salary_summary(text, integer) TO gateway_reader;

CREATE SCHEMA IF NOT EXISTS lab_audit;
REVOKE ALL ON SCHEMA lab_audit FROM PUBLIC, gateway_reader;
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
REVOKE ALL ON lab_audit.events FROM PUBLIC, gateway_reader;
REVOKE ALL (event_id, occurred_at, request_id, actor, action, company_id, status, outcome)
    ON lab_audit.events FROM PUBLIC, gateway_reader;
GRANT USAGE ON SCHEMA lab_audit TO gateway_reader;
GRANT INSERT ON lab_audit.events TO gateway_reader;
REVOKE ALL ON SEQUENCE lab_audit.events_event_id_seq FROM PUBLIC, gateway_reader;
GRANT USAGE ON SEQUENCE lab_audit.events_event_id_seq TO gateway_reader;
