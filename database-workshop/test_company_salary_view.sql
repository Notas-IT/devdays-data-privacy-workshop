\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE
    actual numeric;
    expected numeric;
BEGIN
    IF EXISTS (SELECT FROM private_db.company_average_salary) THEN
        RAISE EXCEPTION 'An unset company ID must return no rows';
    END IF;

    PERFORM set_config('app.company_id', '1', true);
    IF (SELECT count(*) FROM private_db.company_average_salary) <> 1
       OR NOT EXISTS (SELECT FROM private_db.company_average_salary
                      WHERE company_id = 1 AND company_name = 'Daukantas Energy UAB') THEN
        RAISE EXCEPTION 'Only the selected company must be returned';
    END IF;

    SELECT average_salary_eur INTO actual FROM private_db.company_average_salary;
    SELECT round(avg(e.salary_eur), 2) INTO expected
    FROM private_db.employment_contract AS e
    JOIN private_db.company AS c
      ON c.registration_number = e.company_registration_number
    WHERE c.company_id = 1;
    IF actual IS DISTINCT FROM expected THEN
        RAISE EXCEPTION 'The average does not match the selected company';
    END IF;

    PERFORM set_config('app.company_id', '0', true);
    IF EXISTS (SELECT FROM private_db.company_average_salary) THEN
        RAISE EXCEPTION 'An unknown company must return no rows';
    END IF;

    PERFORM set_config('app.company_id', '', true);
    IF EXISTS (SELECT FROM private_db.company_average_salary) THEN
        RAISE EXCEPTION 'An empty company ID must return no rows';
    END IF;

    PERFORM set_config('app.company_id', 'invalid', true);
    BEGIN
        PERFORM * FROM private_db.company_average_salary;
        RAISE EXCEPTION 'An invalid company ID must be rejected';
    EXCEPTION WHEN invalid_text_representation THEN
        NULL;
    END;
END $$;
ROLLBACK;
