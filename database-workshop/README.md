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

- [Intentionally risky schema diagram](docs/intentionally-risky-schema.drawio):
  editable draw.io diagram of the selected tables, privacy risks and linkage path.
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

## Trace Records Instead Of Browsing Every Table

Use the read-only tracer to start with one public person and follow the known
links through this workshop's tables. It creates an offline HTML report with
expandable tables and a JSON report for further analysis. It requires Python 3
and the running Compose Postgres service; no Python packages are needed.

From the repository root:

```bash
python3 database-workshop/trace_data.py trace \
  --person 42 \
  --output-dir database-workshop/reports/before
```

Open `database-workshop/reports/before/trace.html`. Students can inspect:

- The starting public person, candidate professional profiles, public companies and awards.
- Identity candidates matched by name/birth date/postcode, or birth date/postcode/employer/role.
- Shared person and contract IDs, which the original data generator intentionally exposes.
- Connected private identities, contracts, salaries, payroll/bank accounts, benefits, application accounts and company financials.

`--person` selects a **public `people_directory.directory_id`**. Omit it to use
the first available public record. `--limit 10` controls examples shown per
table/path; counts still cover all matching records. The report uses all
candidate paths to find related rows, including candidates beyond the display
limit. Company registration numbers are also followed independently of person
matches. Public employer-name matches can produce multiple companies.

After students create a pseudonymised private copy, trace that schema against
the same unchanged public data. The following assumes their copy is named
`pseudonymised_private` and retains the original table and column layout;
creating that copy is a separate exercise.

```bash
python3 database-workshop/trace_data.py trace \
  --person 42 --private-schema pseudonymised_private \
  --output-dir database-workshop/reports/after

python3 database-workshop/trace_data.py compare \
  database-workshop/reports/before/trace.json \
  database-workshop/reports/after/trace.json \
  --output-dir database-workshop/reports/comparison
```

Open `database-workshop/reports/comparison/comparison.html`. Students compare
candidate counts and actual values, then explain which links survived and why.
For example, name masking may stop the name-based path while shared IDs or
birth date/postcode/job still produce candidates. This is a hypothesis to test
on their copy, not a predetermined result.

A candidate is **not a confirmed identity**, even when there is only one.
Shared IDs can become misleading after remapping. Compare claimed identities
against the instructor's original data or protected mapping after the linkage
attempt; do not give that mapping to students during the attempt. Do not
interpret matching row positions in before/after samples as identity proof.

Zero matches do not prove anonymisation: this tool checks four known matching
paths for one person, not every possible inference. Repeat for multiple public
people. Investigate whether lost links reflect better privacy or broken joins,
and check analytics separately. The original reconstruction view still points
to `private_db`; this command explicitly queries the selected target schema.

The query runs in a read-only snapshot transaction with a statement timeout.
`--db-user` selects the SQL role and the report records its RLS bypass flags;
results reflect that role's visibility, not an API/access-control test. Both
public and target schemas need read access. Other connection options are listed
by `python3 database-workshop/trace_data.py trace --help`.

Reports include the actual values returned by the database. New report folders
are private to the local user, report files have mode `0600`, and `reports/` is
ignored by Git. Treat reports as sensitive if adapting this to real data.

Run the small report tests:

```bash
python3 -m unittest discover -s database-workshop/tests -v
```

To also exercise real PostgreSQL joins, ambiguity, masking and read-only
transactions, start the Postgres service and run:

```bash
WORKSHOP_TRACE_INTEGRATION=1 python3 -m unittest discover -s database-workshop/tests -v
```

Integration tests create and remove their own uniquely named database with
small synthetic fixtures. They never reset the existing workshop database.
The configured `workshop` role needs database creation rights for these tests.

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

