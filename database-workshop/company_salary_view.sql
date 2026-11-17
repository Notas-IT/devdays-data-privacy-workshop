-- No company setting (or an empty setting) returns no rows.
-- This setting must come from trusted application code; callers can otherwise
-- select a different company themselves. It is not authentication.
CREATE OR REPLACE VIEW private_db.company_average_salary
WITH (security_barrier = true) AS
SELECT
    c.company_id,
    c.company_name,
    round(avg(e.salary_eur), 2) AS average_salary_eur
FROM private_db.company AS c
JOIN private_db.employment_contract AS e
    ON e.company_registration_number = c.registration_number
WHERE c.company_id = nullif(current_setting('app.company_id', true), '')::bigint
GROUP BY c.company_id, c.company_name;
