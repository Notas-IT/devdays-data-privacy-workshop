\copy private_db.company FROM '/workshop/generated/private_company.csv' WITH (FORMAT csv, HEADER true);
\copy private_db.person_identity FROM '/workshop/generated/private_person_identity.csv' WITH (FORMAT csv, HEADER true);
\copy private_db.employment_contract FROM '/workshop/generated/private_employment_contract.csv' WITH (FORMAT csv, HEADER true);
\copy private_db.payroll_event FROM '/workshop/generated/private_payroll_event.csv' WITH (FORMAT csv, HEADER true);
\copy private_db.benefit_claim FROM '/workshop/generated/private_benefit_claim.csv' WITH (FORMAT csv, HEADER true);
\copy private_db.application_user FROM '/workshop/generated/private_application_user.csv' WITH (FORMAT csv, HEADER true);

\copy public_db.company_registry FROM '/workshop/generated/public_company_registry.csv' WITH (FORMAT csv, HEADER true);
\copy public_db.people_directory FROM '/workshop/generated/public_people_directory.csv' WITH (FORMAT csv, HEADER true);
\copy public_db.professional_profile FROM '/workshop/generated/public_professional_profile.csv' WITH (FORMAT csv, HEADER true);
\copy public_db.procurement_award FROM '/workshop/generated/public_procurement_award.csv' WITH (FORMAT csv, HEADER true);

\ir company_salary_view.sql
\ir salary_view_access.sql
\ir salary_row_security.sql

