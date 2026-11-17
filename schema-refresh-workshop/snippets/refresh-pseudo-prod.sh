#!/bin/sh
# Compare schemas, then replace pseudo-prod with a verified anonymised clone.
set -eu
snippet_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file="$snippet_dir/../docker-compose.yml"
docker compose -f "$compose_file" build refresh-runner
docker compose -f "$compose_file" --profile refresh up --detach --wait
docker compose -f "$compose_file" run --rm refresh-runner python refresh_pseudo_prod.py
