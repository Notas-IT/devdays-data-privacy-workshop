# Schema Files From The Live Exercise

These files were generated from the workshop's actual PostgreSQL catalogs by
`contract_walkthrough.py --examples DIRECTORY`, using synthetic fixtures.

- `production.previous.json` / `.txt`: baseline source schema after its clone
  was successfully published.
- `production.current.json` / `.txt`: source schema after both migrations add
  four columns to `people`.
- `schema.diff.json`: the four additions, ordered by table and column name.
- `column-mapping.txt`: the starter code's source-to-target column rules.
- `preprod.sql`: the starter target schema generated from Python, including
  primary keys, unique keys, foreign keys and a salary CHECK.

The mapping and target SQL intentionally still describe the baseline. Students
must update `preprod_schema.py` to cover the new columns, or select the supplied
presenter solution. Source rows and pseudonymisation keys are not exported.

Compare the files without PostgreSQL or third-party packages:

```bash
python3 schema_files.py examples/production.previous.json examples/production.current.json
```

Exit status 1 means a schema difference was found; it is expected here.
