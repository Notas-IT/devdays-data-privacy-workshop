-- Synthetic workshop login. Keep the workshop administrator for setup only.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'salary_viewer') THEN
        CREATE ROLE salary_viewer LOGIN;
    END IF;
END $$;

ALTER ROLE salary_viewer WITH LOGIN PASSWORD 'salary-viewer-demo'
    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT;

REVOKE ALL ON ALL TABLES IN SCHEMA private_db FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA private_db FROM salary_viewer;
REVOKE ALL ON SCHEMA private_db FROM salary_viewer;
GRANT CONNECT ON DATABASE privacy_workshop TO salary_viewer;
GRANT USAGE ON SCHEMA private_db TO salary_viewer;
GRANT SELECT ON private_db.company_average_salary TO salary_viewer;
