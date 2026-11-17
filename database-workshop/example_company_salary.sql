BEGIN;
SET LOCAL app.company_id = '1';
SELECT * FROM private_db.company_average_salary;
COMMIT;
