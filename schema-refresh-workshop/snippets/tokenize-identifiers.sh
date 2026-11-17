#!/bin/sh
# Update pseudo-prod, verify HMACs, and run the related tests. Source data is read-only.
set -eu
snippet_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file="$snippet_dir/../docker-compose.yml"
docker compose -f "$compose_file" build refresh-runner
docker compose -f "$compose_file" --profile refresh up --detach --wait
docker compose -f "$compose_file" run --rm refresh-runner python tokenize_pseudo_prod.py tokenize
docker compose -f "$compose_file" run --rm refresh-runner python tokenize_pseudo_prod.py verify
docker compose -f "$compose_file" run --rm refresh-runner python -m unittest discover -s tests -p test_tokenization.py -v
