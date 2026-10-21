-- Stage 1: Agent process
-- This stage is independent. Reapplying it restores its declared grants.
REVOKE SELECT ON lab_private.employee_salaries FROM gateway_reader;
REVOKE USAGE ON SCHEMA lab_private FROM gateway_reader;
DROP POLICY IF EXISTS layer_direct ON lab_private.employee_salaries;
REVOKE EXECUTE ON FUNCTION lab_api.salary_rows(integer),
    lab_api.open_salary_summary(integer), lab_api.authenticate(text),
    lab_api.salary_summary(text,integer) FROM gateway_reader;
REVOKE INSERT ON lab_audit.events FROM gateway_reader;
GRANT USAGE ON SCHEMA lab_private TO gateway_reader;
GRANT SELECT ON lab_private.employee_salaries TO gateway_reader;
CREATE POLICY layer_direct ON lab_private.employee_salaries FOR SELECT TO gateway_reader USING (true);
