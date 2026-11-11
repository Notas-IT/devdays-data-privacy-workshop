DROP SCHEMA IF EXISTS private_db CASCADE;
DROP SCHEMA IF EXISTS public_db CASCADE;

CREATE SCHEMA private_db;
CREATE SCHEMA public_db;

CREATE TABLE private_db.person_identity (
    person_id BIGINT PRIMARY KEY,
    national_id TEXT NOT NULL UNIQUE,
    tax_id TEXT NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    date_of_birth DATE NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL UNIQUE,
    home_street TEXT NOT NULL,
    home_city TEXT NOT NULL,
    home_postcode TEXT NOT NULL
);

CREATE TABLE private_db.company (
    company_id BIGINT PRIMARY KEY,
    registration_number TEXT NOT NULL UNIQUE,
    company_name TEXT NOT NULL,
    industry TEXT NOT NULL,
    headquarters_city TEXT NOT NULL,
    employee_count INTEGER NOT NULL CHECK (employee_count > 0),
    annual_revenue_eur BIGINT NOT NULL CHECK (annual_revenue_eur >= 0),
    annual_profit_eur BIGINT NOT NULL
);

CREATE TABLE private_db.employment_contract (
    contract_id BIGINT PRIMARY KEY,
    national_id TEXT NOT NULL,
    employee_email TEXT NOT NULL,
    company_registration_number TEXT NOT NULL,
    role_title TEXT NOT NULL,
    department TEXT NOT NULL,
    employment_start_date DATE NOT NULL,
    salary_eur INTEGER NOT NULL CHECK (salary_eur > 0),
    bonus_eur INTEGER NOT NULL CHECK (bonus_eur >= 0),
    manager_email TEXT,
    CONSTRAINT employment_identity_join
        FOREIGN KEY (national_id) REFERENCES private_db.person_identity (national_id),
    CONSTRAINT employment_email_join
        FOREIGN KEY (employee_email) REFERENCES private_db.person_identity (email),
    CONSTRAINT employment_company_join
        FOREIGN KEY (company_registration_number) REFERENCES private_db.company (registration_number)
);

CREATE TABLE private_db.payroll_event (
    payroll_event_id BIGINT PRIMARY KEY,
    employee_email TEXT NOT NULL,
    payroll_month DATE NOT NULL,
    gross_pay_eur INTEGER NOT NULL CHECK (gross_pay_eur >= 0),
    tax_withheld_eur INTEGER NOT NULL CHECK (tax_withheld_eur >= 0),
    bank_account TEXT NOT NULL,
    CONSTRAINT payroll_email_join
        FOREIGN KEY (employee_email) REFERENCES private_db.person_identity (email)
);

CREATE TABLE private_db.benefit_claim (
    claim_id BIGINT PRIMARY KEY,
    claimant_phone TEXT NOT NULL,
    claim_date DATE NOT NULL,
    condition_category TEXT NOT NULL,
    provider_city TEXT NOT NULL,
    amount_eur INTEGER NOT NULL CHECK (amount_eur >= 0),
    approved BOOLEAN NOT NULL,
    CONSTRAINT claim_phone_join
        FOREIGN KEY (claimant_phone) REFERENCES private_db.person_identity (phone)
);

CREATE TABLE private_db.application_user (
    user_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    permission_group TEXT NOT NULL,
    can_view_salary BOOLEAN NOT NULL,
    can_view_company_financials BOOLEAN NOT NULL,
    CONSTRAINT user_email_join
        FOREIGN KEY (email) REFERENCES private_db.person_identity (email)
);

CREATE TABLE public_db.people_directory (
    directory_id BIGINT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    date_of_birth DATE NOT NULL,
    city TEXT NOT NULL,
    postcode TEXT NOT NULL,
    public_profile_url TEXT NOT NULL
);

CREATE TABLE public_db.professional_profile (
    profile_id BIGINT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    city TEXT NOT NULL,
    postcode TEXT NOT NULL,
    employer_name TEXT NOT NULL,
    role_title TEXT NOT NULL,
    seniority TEXT NOT NULL,
    salary_band TEXT NOT NULL,
    public_profile_url TEXT NOT NULL
);

CREATE TABLE public_db.company_registry (
    registry_id BIGINT PRIMARY KEY,
    registration_number TEXT NOT NULL UNIQUE,
    company_name TEXT NOT NULL,
    industry TEXT NOT NULL,
    city TEXT NOT NULL,
    employee_count_band TEXT NOT NULL,
    revenue_band TEXT NOT NULL,
    profit_band TEXT NOT NULL
);

CREATE TABLE public_db.procurement_award (
    award_id BIGINT PRIMARY KEY,
    registration_number TEXT NOT NULL,
    award_date DATE NOT NULL,
    buyer_name TEXT NOT NULL,
    award_category TEXT NOT NULL,
    award_value_eur INTEGER NOT NULL CHECK (award_value_eur > 0),
    CONSTRAINT award_company_join
        FOREIGN KEY (registration_number) REFERENCES public_db.company_registry (registration_number)
);

CREATE INDEX idx_private_identity_name_dob
    ON private_db.person_identity (last_name, first_name, date_of_birth);

CREATE INDEX idx_private_identity_contact
    ON private_db.person_identity (email, phone, national_id);

CREATE INDEX idx_private_employment_pii
    ON private_db.employment_contract (national_id, employee_email, company_registration_number);

CREATE INDEX idx_private_payroll_email_month
    ON private_db.payroll_event (employee_email, payroll_month);

CREATE INDEX idx_private_claim_phone
    ON private_db.benefit_claim (claimant_phone);

CREATE INDEX idx_public_directory_quasi
    ON public_db.people_directory (last_name, first_name, date_of_birth, postcode);

CREATE INDEX idx_public_profile_quasi
    ON public_db.professional_profile (last_name, first_name, postcode, employer_name, role_title);

CREATE INDEX idx_public_company_registry_number
    ON public_db.company_registry (registration_number);
