#!/bin/sh
# Apply the requested constants, verify them, then run all schema-refresh tests.
set -eu
snippet_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file="$snippet_dir/../docker-compose.yml"
docker compose -f "$compose_file" build refresh-runner
docker compose -f "$compose_file" --profile refresh up --detach --wait
docker compose -f "$compose_file" run --rm refresh-runner python mask_pseudo_prod.py apply
docker compose -f "$compose_file" run --rm refresh-runner python mask_pseudo_prod.py verify
docker compose -f "$compose_file" run --rm refresh-runner python -m unittest discover -s tests -v
