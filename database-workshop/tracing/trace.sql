-- Values and schema identifiers are supplied with psql variables, never SQL interpolation.
-- Every count covers the full matching set; only displayed rows are limited.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '60s';
WITH
seed AS MATERIALIZED (
    SELECT * FROM :"public_schema".people_directory
    WHERE NULLIF(:'person_id', '') IS NULL OR directory_id = NULLIF(:'person_id', '')::bigint
    ORDER BY directory_id LIMIT 1
),
profiles AS MATERIALIZED (
    SELECT pp.* FROM :"public_schema".professional_profile pp
    WHERE EXISTS (SELECT FROM seed s WHERE pp.public_profile_url = s.public_profile_url
        OR (pp.first_name = s.first_name AND pp.last_name = s.last_name AND pp.postcode = s.postcode))
),
registries AS MATERIALIZED (
    SELECT c.* FROM :"public_schema".company_registry c
    WHERE EXISTS (SELECT FROM profiles p WHERE p.employer_name = c.company_name)
),
methods(path, explanation) AS (VALUES
    ('name_birth_postcode', 'Public first name + last name + birth date + postcode match private identity.'),
    ('birth_postcode_job', 'Birth date + postcode + employer + role match, without using private names.'),
    ('preserved_person_id', 'Hypothesis: public directory_id equals private person_id. The original generator shares these IDs.'),
    ('preserved_contract_id', 'Hypothesis: public directory_id equals private contract_id; follow national ID or email to identity.')
),
matches AS MATERIALIZED (
    SELECT 'name_birth_postcode' AS path, p.person_id
    FROM :"private_schema".person_identity p JOIN seed s
      ON p.first_name = s.first_name AND p.last_name = s.last_name
      AND p.date_of_birth = s.date_of_birth AND p.home_postcode = s.postcode
    UNION
    SELECT 'birth_postcode_job', p.person_id
    FROM :"private_schema".person_identity p JOIN seed s
      ON p.date_of_birth = s.date_of_birth AND p.home_postcode = s.postcode
    WHERE EXISTS (
      SELECT FROM :"private_schema".employment_contract e
      JOIN :"private_schema".company c ON c.registration_number = e.company_registration_number
      JOIN profiles pp ON pp.employer_name = c.company_name AND pp.role_title = e.role_title
      WHERE e.national_id = p.national_id OR e.employee_email = p.email
    )
    UNION
    SELECT 'preserved_person_id', p.person_id
    FROM :"private_schema".person_identity p JOIN seed s ON p.person_id::text = s.directory_id::text
    UNION
    SELECT 'preserved_contract_id', p.person_id
    FROM :"private_schema".employment_contract e JOIN seed s ON e.contract_id::text = s.directory_id::text
    JOIN :"private_schema".person_identity p ON p.national_id = e.national_id OR p.email = e.employee_email
),
people AS MATERIALIZED (
    SELECT p.* FROM :"private_schema".person_identity p
    WHERE EXISTS (SELECT FROM matches m WHERE m.person_id = p.person_id)
),
contracts AS MATERIALIZED (
    SELECT e.* FROM :"private_schema".employment_contract e
    WHERE EXISTS (SELECT FROM people p WHERE p.national_id = e.national_id OR p.email = e.employee_email)
       OR EXISTS (SELECT FROM seed s WHERE e.contract_id::text = s.directory_id::text)
),
payroll AS MATERIALIZED (
    SELECT e.* FROM :"private_schema".payroll_event e
    WHERE EXISTS (SELECT FROM people p WHERE p.email = e.employee_email)
),
claims AS MATERIALIZED (
    SELECT e.* FROM :"private_schema".benefit_claim e
    WHERE EXISTS (SELECT FROM people p WHERE p.phone = e.claimant_phone)
),
users AS MATERIALIZED (
    SELECT e.* FROM :"private_schema".application_user e
    WHERE EXISTS (SELECT FROM people p WHERE p.email = e.email)
),
companies AS MATERIALIZED (
    SELECT c.* FROM :"private_schema".company c
    WHERE EXISTS (SELECT FROM contracts e WHERE e.company_registration_number = c.registration_number)
       OR EXISTS (SELECT FROM registries r WHERE r.registration_number = c.registration_number)
),
awards AS MATERIALIZED (
    SELECT a.* FROM :"public_schema".procurement_award a
    WHERE EXISTS (SELECT FROM registries r WHERE r.registration_number = a.registration_number)
)
SELECT jsonb_build_object(
    'format_version', 1,
    'database', current_database(), 'database_user', current_user,
    'role', (SELECT jsonb_build_object('superuser', rolsuper, 'bypass_rls', rolbypassrls)
             FROM pg_roles WHERE rolname = current_user),
    'private_schema', :'private_schema', 'public_schema', :'public_schema',
    'limit', :'row_limit'::integer,
    'seed', (SELECT to_jsonb(s) FROM seed s),
    'methods', (SELECT jsonb_agg(jsonb_build_object(
        'path', t.path, 'explanation', t.explanation,
        'candidate_count', (SELECT count(*) FROM matches m WHERE m.path = t.path),
        'candidate_ids', (SELECT COALESCE(jsonb_agg(x.person_id), '[]'::jsonb) FROM
            (SELECT person_id FROM matches m WHERE m.path = t.path ORDER BY person_id LIMIT :'row_limit'::integer) x)
    ) ORDER BY t.path) FROM methods t),
    'tables', __TABLE_REPORTS__
);
ROLLBACK;
