#!/bin/sh
# Generate the pseudo-prod description, verify reproducibility, and run its tests.
set -eu
snippet_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file="$snippet_dir/../docker-compose.yml"
docker compose -f "$compose_file" run --rm refresh-runner python describe_schema.py
docker compose -f "$compose_file" run --rm refresh-runner python -c '
import os
from pathlib import Path
import psycopg
from describe_schema import read_schema, render_schema

with psycopg.connect(os.environ["PSEUDO_PROD_DSN"], autocommit=True) as connection:
    regenerated = render_schema(read_schema(connection)).encode("utf-8")
if Path("pseudo-prod.schema.txt").read_bytes() != regenerated:
    raise SystemExit("FAIL: generated descriptions differ")
print("PASS: repeated generation is byte-for-byte identical")
'
docker compose -f "$compose_file" run --rm refresh-runner python -m unittest discover -s tests -p test_schema_description.py -v
