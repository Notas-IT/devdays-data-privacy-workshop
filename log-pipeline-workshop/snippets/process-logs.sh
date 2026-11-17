#!/bin/sh
# Start the full pipeline and show only sanitised output from its two routes.
set -eu
snippet_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file="$snippet_dir/../docker-compose.yml"
docker compose -f "$compose_file" --profile pipeline up --detach --build --wait
echo 'Watching sanitised logs: processing_path is regex or presidio. Ctrl+C stops watching.'
docker compose -f "$compose_file" logs --follow --tail 10 processor log-presidio
