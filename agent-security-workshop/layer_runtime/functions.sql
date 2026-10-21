-- Stage 5: approved row access, before the aggregate-only boundary is added.
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='layer_row_reader') THEN
        CREATE ROLE layer_row_reader NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END $$;
GRANT USAGE ON SCHEMA lab_private, lab_api TO layer_row_reader;
GRANT SELECT(employee_id, company_id, employee_name, salary_eur)
    ON lab_private.employee_salaries TO layer_row_reader;
DROP POLICY IF EXISTS layer_rows ON lab_private.employee_salaries;
CREATE POLICY layer_rows ON lab_private.employee_salaries FOR SELECT TO layer_row_reader
    USING (company_id = nullif(current_setting('app.company_id', true), '')::integer);

CREATE OR REPLACE FUNCTION lab_api.salary_rows(p_company_id integer)
RETURNS TABLE(employee_id integer, company_id integer, employee_name text, salary_eur integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM set_config('app.company_id', p_company_id::text, true);
    RETURN QUERY SELECT e.employee_id,e.company_id,e.employee_name,e.salary_eur
        FROM lab_private.employee_salaries e;
END $$;
ALTER FUNCTION lab_api.salary_rows(integer) OWNER TO layer_row_reader;
REVOKE ALL ON FUNCTION lab_api.salary_rows(integer) FROM PUBLIC;

-- Stage 6: fixed aggregate shape, but no per-person identity until stage 7.
CREATE OR REPLACE FUNCTION lab_api.open_salary_summary(p_company_id integer)
RETURNS TABLE(company_id integer, employee_count bigint, average_salary_eur numeric)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM set_config('app.company_id', p_company_id::text, true);
    RETURN QUERY SELECT e.company_id,count(*),avg(e.salary_eur)
        FROM lab_private.employee_salaries e
        GROUP BY e.company_id HAVING count(*) >= 3;
END $$;
ALTER FUNCTION lab_api.open_salary_summary(integer) OWNER TO lab_summary;
REVOKE ALL ON FUNCTION lab_api.open_salary_summary(integer) FROM PUBLIC;
