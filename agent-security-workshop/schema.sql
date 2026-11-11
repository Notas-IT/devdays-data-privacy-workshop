CREATE SCHEMA lab_public;
CREATE SCHEMA lab_private;

CREATE TABLE lab_public.projects (
    project_id integer PRIMARY KEY,
    title text NOT NULL
);
CREATE TABLE lab_private.employee_salaries (
    employee_id integer PRIMARY KEY,
    company_id integer NOT NULL,
    employee_name text NOT NULL,
    salary_eur integer NOT NULL,
    security_canary text
);
INSERT INTO lab_public.projects VALUES
    (1, 'Conference schedule'), (2, 'Workshop materials');
INSERT INTO lab_private.employee_salaries VALUES
    (101, 1, 'Demo A', 3000, NULL),
    (102, 1, 'Demo B', 4000, NULL),
    (103, 1, 'Demo C', 5000, NULL),
    (9001, 2, 'Demo D', 9999, encode(sha256(random()::text::bytea), 'hex')),
    (9002, 2, 'Demo E', 6000, NULL),
    (9003, 2, 'Demo F', 7000, NULL),
    (301, 3, 'Demo G', 8000, NULL);
