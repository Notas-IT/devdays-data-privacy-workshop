# Database Anonymisation Workshop

This repository contains a synthetic Postgres dataset for anonymisation exercises.

The setup creates two logical databases inside one Postgres database:

- `private_db`: the internal company/person database attendees will anonymise.
- `public_db`: public reference data that can be used to reconstruct sensitive facts when anonymisation is weak.

The data is fake, deterministic, and generated locally. The default generator size is 100,000 people.

## Why The Model Is Risky

The schema is intentionally designed for privacy training:

- Some private tables join through direct PII such as `national_id`, `email`, and `phone`.
- Some public tables contain quasi-identifiers such as name, birth date, postcode, employer, role, and city.
- If attendees anonymise each table independently, relationships can break.
- If they preserve too much detail, public data can re-identify people and recover salaries, claims, company revenue, or profit.

## Files

- `schema.sql`: Postgres schema, indexes, views, and constraints.
- `generate_data.py`: deterministic CSV generator for 100k synthetic records.
- `load_data.sql`: psql script that imports generated CSV files.
- `docker-compose.yml`: optional local Postgres instance for the workshop.

## Quick Start

Run these commands from this workshop directory:

```bash
cd database-workshop
```

Start Postgres:

```bash
docker compose up -d
```

Generate 100k records:

```bash
python3 generate_data.py --people 100000 --out generated
```

Create schema and load data:

```bash
docker compose exec -T postgres psql -U workshop -d privacy_workshop -f /workshop/schema.sql
docker compose exec -T postgres psql -U workshop -d privacy_workshop -f /workshop/load_data.sql
```

`schema.sql` resets the workshop schemas. Apply it and load data only when
initialising or resetting the exercise.

Connect at `localhost:5432`, database `privacy_workshop`, username `workshop`,
password `workshop`. This Docker setup retains the original Compose project
name and data volume, so the already loaded database remains available.

Try a reconstruction query:

```sql
SELECT *
FROM exercise.reidentify_salary_from_public
LIMIT 20;
```

## Suggested Exercise

1. Give attendees access only to `private_db`.
2. Ask them to anonymise it while preserving analytics:
   - salary distribution by role, city, age band, and company size
   - claim totals by condition category and employer industry
   - company profit visibility only for permitted users
3. After anonymisation, join the result against `public_db`.
4. Discuss which fields must be generalised, bucketed, suppressed, consistently pseudonymised, or access-controlled.

## Access Protection Workshop

The [protection workshop](protection/README.md) adds restricted SQL users, a
table-owner bypass demonstration, and an authenticated API with configurable
salary/company permissions and durable audit logging. It uses the loaded data
without regenerating it:

```bash
docker compose build db-security-tools privacy-api
docker compose run --rm db-security-tools init
docker compose run --rm db-security-tools owner-demo
docker compose up -d privacy-api
docker compose run --rm db-security-tools api-demo
docker compose run --rm --entrypoint pytest db-security-tools -q
```

API documentation is at http://localhost:18000/docs. Demo API users include
`employee_a`, `hr_a`, `finance_a`, `admin` and `auditor`; their password is
`Workshop!2026`. These are intentionally published local workshop credentials.

