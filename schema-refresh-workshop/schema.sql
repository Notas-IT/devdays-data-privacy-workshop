DROP SCHEMA IF EXISTS business CASCADE;
CREATE SCHEMA business;
REVOKE ALL ON SCHEMA business FROM PUBLIC;

CREATE TABLE business.companies (
    company_id BIGINT PRIMARY KEY,
    company_name TEXT NOT NULL,
    annual_profit_eur INTEGER NOT NULL
);

CREATE TABLE business.people (
    person_id BIGINT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    national_id TEXT NOT NULL UNIQUE,
    birth_date DATE NOT NULL
);

CREATE TABLE business.employment (
    contract_id BIGINT PRIMARY KEY,
    employee_email TEXT NOT NULL REFERENCES business.people(email),
    company_id BIGINT NOT NULL REFERENCES business.companies(company_id),
    salary_eur INTEGER NOT NULL CHECK (salary_eur > 0),
    department TEXT NOT NULL
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'production_reader') THEN
        CREATE ROLE production_reader LOGIN PASSWORD 'reader-demo';
    END IF;
END $$;
GRANT USAGE ON SCHEMA business TO production_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA business TO production_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA business GRANT SELECT ON TABLES TO production_reader;
