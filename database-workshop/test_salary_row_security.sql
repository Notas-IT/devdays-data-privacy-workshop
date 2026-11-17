\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL ROLE salary_summary_owner;

DO $$
BEGIN
    IF NOT row_security_active('private_db.company')
       OR NOT row_security_active('private_db.employment_contract') THEN
        RAISE EXCEPTION 'Both tables must enforce RLS for the view owner';
    END IF;

    IF EXISTS (SELECT FROM private_db.company)
       OR EXISTS (SELECT FROM private_db.employment_contract) THEN
        RAISE EXCEPTION 'Unset company context must hide all rows';
    END IF;

    PERFORM set_config('app.company_id', '1', true);
    IF (SELECT count(*) FROM private_db.company) <> 1
       OR NOT EXISTS (SELECT FROM private_db.company
                      WHERE company_id = 1 AND company_name = 'Daukantas Energy UAB') THEN
        RAISE EXCEPTION 'Company context must expose only the selected company';
    END IF;
    IF NOT EXISTS (SELECT FROM private_db.employment_contract
                   WHERE company_registration_number = 'CR00000001') THEN
        RAISE EXCEPTION 'The selected company must have salary rows';
    END IF;
    IF EXISTS (SELECT FROM private_db.employment_contract
               WHERE company_registration_number <> 'CR00000001') THEN
        RAISE EXCEPTION 'Salary rows from other companies must be hidden';
    END IF;

    PERFORM set_config('app.company_id', '0', true);
    IF EXISTS (SELECT FROM private_db.company)
       OR EXISTS (SELECT FROM private_db.employment_contract) THEN
        RAISE EXCEPTION 'Unknown company context must hide all rows';
    END IF;

    PERFORM set_config('app.company_id', '', true);
    IF EXISTS (SELECT FROM private_db.company)
       OR EXISTS (SELECT FROM private_db.employment_contract) THEN
        RAISE EXCEPTION 'Empty company context must hide all rows';
    END IF;
END $$;

ROLLBACK;
