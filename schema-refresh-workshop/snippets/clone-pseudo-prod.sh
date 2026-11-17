#!/usr/bin/env bash
# Copy the original schema-refresh database. This does not anonymise any data.
set -euo pipefail

snippet_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file="$snippet_dir/../docker-compose.yml"
compose() { docker compose -f "$compose_file" "$@"; }

compose --profile refresh up --detach --wait

exists=$(compose exec -T refresh-preprod psql -X -q -A -t \
    -v ON_ERROR_STOP=1 -U preprod_admin -d postgres \
    -c "SELECT 1 FROM pg_database WHERE datname='pseudo-prod';")
if [[ "$exists" == "1" ]]; then
    echo 'STOP: pseudo-prod already exists; no database was overwritten.' >&2
    exit 1
fi

clone_temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/workshop-clone.XXXXXX")
trap 'rm -rf -- "$clone_temp_dir"' EXIT

echo 'Copying production schema and data...'
compose exec -T refresh-prod pg_dump -U production_admin -d production \
    --format=custom --no-owner --no-acl > "$clone_temp_dir/source.dump"

compose exec -T refresh-preprod createdb -U preprod_admin \
    --template=template0 --owner=preprod_admin pseudo-prod
compose exec -T refresh-preprod pg_restore -U preprod_admin -d pseudo-prod \
    --single-transaction --exit-on-error --no-owner --no-acl < "$clone_temp_dir/source.dump"

echo 'Comparing source and clone table contents...'
compose exec -T refresh-prod psql -X -q -A -t -v ON_ERROR_STOP=1 \
    -U production_admin -d production \
    < "$snippet_dir/clone-manifest.sql" > "$clone_temp_dir/source.manifest"
compose exec -T refresh-preprod psql -X -q -A -t -v ON_ERROR_STOP=1 \
    -U preprod_admin -d pseudo-prod \
    < "$snippet_dir/clone-manifest.sql" > "$clone_temp_dir/clone.manifest"

if ! cmp -s "$clone_temp_dir/source.manifest" "$clone_temp_dir/clone.manifest"; then
    echo 'FAIL: source and clone differ. Check whether the source changed during cloning.' >&2
    exit 1
fi

while IFS='|' read -r table rows checksum; do
    printf 'PASS: %s — %s rows copied\n' "$table" "$rows"
done < "$clone_temp_dir/clone.manifest"
echo 'PASS: pseudo-prod created and table contents verified.'
