# Build A Reusable Pseudonymised Database Refresh

Build a repeatable refresh with two independent definitions: what production
currently contains, and what preprod is allowed to contain. The starter and
working implementation are included. Students extend the code when production
changes; new fields are never silently copied.

Open the editable [process diagram](docs/code-defined-refresh.drawio) in
draw.io / diagrams.net. [Generated example files](examples/) show a real schema
comparison without needing to start Docker.

## 1. Start With A Known Production Schema

Run from `schema-refresh-workshop/`:

```bash
docker compose build refresh-runner
docker compose --profile refresh up -d refresh-prod refresh-preprod
docker compose run --rm refresh-runner python refresh.py init
docker compose run --rm refresh-runner python contract_refresh.py inspect
docker compose run --rm refresh-runner python contract_refresh.py refresh
```

`init` resets this workshop's synthetic production/preprod schemas. Use it at
the beginning of the exercise, not during a refresh of a database you want to
retain. Stop the old `refresh-scheduler` first if it is running; it implements
the separate automatic-detection exercise.

Open `artifacts/production.current.txt`. Tables and columns are sorted
alphabetically, and every column has its PostgreSQL type and nullability:

```text
business.companies
  annual_profit_eur: integer NOT NULL
  company_id: bigint NOT NULL
  company_name: text NOT NULL

business.employment
  company_id: bigint NOT NULL
  contract_id: bigint NOT NULL
  department: text NOT NULL
  employee_email: text NOT NULL
  salary_eur: integer NOT NULL
```

The JSON counterpart also stores metadata needed to detect changed types,
nullability, defaults, generated columns and constraints. Default expressions
and constraint expressions are fingerprinted instead of storing their literal
contents. Row values and HMAC keys are never put in these schema files.

On the first run there is no previous snapshot. After a successful refresh,
`production.previous.json` records the source schema of the published clone.
An inspection or failed refresh never advances that file. The files contain
schema metadata, so still limit access if your table/column names are sensitive.

## 2. Read The Target Schema And Column Rules

Edit [preprod_schema.py](preprod_schema.py). This file is the target schema's
source of truth: table names, column names/types, primary keys, unique keys,
foreign keys, CHECK constraints and transformation rules all live in code.

```python
"email": Column("email", "text", token_email("email")),
"first_name": Column("first_name", "text", constant("Person")),
"person_id": Column("person_id", "bigint", keep()),
```

Read each entry as:

```text
target column -> source column + PostgreSQL type + transformation + nullability
```

The employment email uses the same `token_email("email")` rule as the person's
email. The shared scope preserves the foreign-key relationship. A different
scope is rejected before copying. The source and target column names may
differ; update the target keys/references when renaming an output column.

| Rule | Behaviour |
| --- | --- |
| `keep()` | Explicitly copy the value |
| `keep(domain={...})` | Copy only permitted values; reject the refresh if any non-null value falls outside the domain |
| `constant(value)` | Replace every non-null value with that constant; constant masking |
| `null()` | Clear a nullable column |
| `token_email(scope)` | Consistent HMAC email token |
| `token_id(scope)` | Consistent HMAC identifier token |
| `Table(..., omit={"column": "reason"})` | Acknowledge a source column and exclude it from the target entirely |

`constant()` preserves an original NULL. This starter requires source and
target column types/nullability to match; it does not implement arbitrary
type conversion, aggregation or multi-table queries.

Read `artifacts/column-mapping.txt` to see every source-to-target link and rule.
`artifacts/preprod.sql` is generated from the Python definition. Editing that
SQL file does not change the refresh; edit the Python definition instead.
CHECK expressions in that module are trusted application code, not user input.
The module is mounted read-only into the runner, so host edits take effect on
the next run without rebuilding the image.

## 3. Change Production And Read The Diff

```bash
docker compose run --rm refresh-runner python refresh.py migrate new-columns
docker compose run --rm refresh-runner python refresh.py migrate ambiguous
docker compose run --rm refresh-runner python contract_refresh.py inspect
```

The last command intentionally exits with status **2**. Production now has
four columns missing from the code definition. Review `schema.diff.json` and
`refresh.plan.json` in `artifacts/`. The diff reports added/removed tables,
added/removed/changed columns, and constraint changes. Renames are reported as
a removal and an addition; no transformation is guessed.

You can also compare any two exported files offline, using only Python:

```bash
python3 schema_files.py examples/production.previous.json examples/production.current.json
```

The comparison exits **1** when files differ, or **0** when their schemas match.
Use `--output diff.json` to save the result. JSON key order, catalog row order
and physical column order do not create noise in generated snapshots.

## 4. Give Every New Field A Decision

Student tasks:

1. Clear `emergency_contact_email` using a nullable text column and `null()`.
2. Clear nested `payload` using a nullable `jsonb` column and `null()`.
3. Keep `favorite_color`, restricted to `red`, `green` and `blue`.
4. Decide that `internal_memo` is unnecessary and clear or explicitly omit it.
5. Rerun inspection; explain each source-to-target mapping before refreshing.

For example, import `null` and add this inside the `people` table's columns:

```python
"payload": Column("payload", "jsonb", null(), nullable=True),
```

Then run:

```bash
docker compose run --rm refresh-runner python contract_refresh.py inspect
docker compose run --rm refresh-runner python contract_refresh.py refresh
docker compose run --rm refresh-runner python refresh.py verify
```

The original verifier expects the three sensitive fields to exist as NULL
columns. If choosing omission instead, also update verification to assert the
column is absent; an obsolete verifier should not dictate the target design.

A complete presenter solution for all four additions is supplied separately:

```bash
docker compose run --rm refresh-runner python contract_refresh.py refresh --definition solutions.preprod_schema_after_drift
```

## 5. Verify Failure Preserves The Published Clone

Change the salary constant to zero and try a refresh. The code-defined
`salary_eur > 0` CHECK must reject publication. Restore `3500` afterward.
Also try a different email-token scope on one side of the relationship;
inspection must reject it before any target writes.

The live acceptance script covers both failures, an out-of-domain color,
missing column rules, unchanged previous snapshots on failure, preserved
joins, and an actual renamed target column:

```bash
docker compose run --rm refresh-runner python -m pytest -q
docker compose run --rm refresh-runner python contract_walkthrough.py
```

The walkthrough resets this workshop's synthetic fixtures. It uses a temporary
artifact directory and leaves a working clone containing all four new columns.

## Reuse Beyond The Workshop

Point `SOURCE_DSN` at a read-only source connection and `TARGET_DSN` at a
separate target database. Set `SOURCE_SCHEMA` if the source schema is not
`business`. Define `TARGET_SCHEMA`, `VIEWER_ROLE` and `SCHEMA` in your own Python
module, and select it with `--definition your_module`. Provision that viewer
role, a persistent `/state/pseudonym.key`, and a writable artifact directory
before refreshing. The workshop's `init` command is a fixture helper, not a
production onboarding command. `--artifacts DIRECTORY` selects another
snapshot directory; use a separate directory for each source/target pair.

Schema diffing is evidence for review, not a detector of personal data. The
code gate requires explicit column coverage and matching types/nullability;
source constraint changes are reported, while target constraints come only
from code and are validated during publication. Review those diffs too.
Unsupported types, defaults, generated/identity columns and cross-schema
foreign keys remain blocked by the existing catalog checks.

The source is read under one read-only repeatable-read snapshot. Transformations
happen before data enters restricted target staging. Row counts and target
constraints are checked before an atomic schema replacement. The previous
snapshot is saved only after the target transaction commits; a filesystem
failure at that point can leave an older baseline even though publication
succeeded, so reconcile the artifact and target before a further refresh.
The advisory publication lock is shared with the original cloner, but run one
worker per artifact directory to avoid competing inspection reports.

Keeping IDs and stable tokens makes this a **pseudonymised, masked test copy**.
It is not proof of anonymity. The salary constant preserves a valid test value,
not the production salary distribution. The old `refresh.py` policy/detection
exercise remains separate; do not alternate its scheduler with this exercise's
code-defined publisher on the same target.
