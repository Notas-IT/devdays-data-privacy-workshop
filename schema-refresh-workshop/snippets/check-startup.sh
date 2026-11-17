#!/bin/sh
# Build the runner and check both databases without changing workshop data.
set -eu

# Resolve the Compose file relative to this script, regardless of the current folder.
snippet_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file="$snippet_dir/../docker-compose.yml"

docker compose -f "$compose_file" build refresh-runner
docker compose -f "$compose_file" --profile refresh up --detach --wait
docker compose -f "$compose_file" run --rm refresh-runner python -c '
import os, psycopg

for name, setting in [
    ("production", "SOURCE_ADMIN_DSN"),
    ("preprod", "TARGET_DSN"),
]:
    with psycopg.connect(os.environ[setting], connect_timeout=5) as db:
        assert db.execute("SELECT 1").fetchone() == (1,)
    print(f"PASS: {name} database is reachable")

print("PASS: build and startup checks completed")
'
