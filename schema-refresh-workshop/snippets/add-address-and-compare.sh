#!/bin/sh
# Change production only, then export both schemas and demonstrate the drift.
set -eu
snippet_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
workshop_dir=$(CDPATH= cd -- "$snippet_dir/.." && pwd)
compose_file="$workshop_dir/docker-compose.yml"

docker compose -f "$compose_file" --profile refresh up --detach --wait
docker compose -f "$compose_file" exec -T refresh-prod \
    psql -X -v ON_ERROR_STOP=1 -U production_admin -d production \
    < "$workshop_dir/migrations/add_address.sql"
docker compose -f "$compose_file" run --rm refresh-runner python describe_schema.py \
    --dsn-env SOURCE_DSN --output original.schema.txt
docker compose -f "$compose_file" run --rm refresh-runner python describe_schema.py \
    --dsn-env PSEUDO_PROD_DSN --output pseudo-prod.schema.txt

# A difference is expected here. Keep actual comparison errors distinct.
if python3 "$workshop_dir/compare_schemas.py" \
    "$workshop_dir/pseudo-prod.schema.txt" "$workshop_dir/original.schema.txt" \
    --output "$workshop_dir/schema.diff"; then
    echo 'FAIL: schemas unexpectedly match.' >&2
    exit 1
else
    comparison_status=$?
    if [ "$comparison_status" -ne 1 ]; then
        exit "$comparison_status"
    fi
fi
echo 'PASS: original and pseudo-prod schemas differ; see schema.diff.'
