#!/bin/sh
# Usage: sh log-pipeline-workshop/snippets/pulse-logs.sh [seconds]
set -eu

if [ "$#" -gt 1 ]; then
    echo "Usage: $0 [positive whole number of seconds]" >&2
    exit 2
fi
interval=${1:-2}
case "$interval" in
    ''|*[!0-9]*) echo 'Interval must be a positive whole number of seconds.' >&2; exit 2 ;;
esac
if ! [ "$interval" -gt 0 ] 2>/dev/null; then
    echo 'Interval must be a positive whole number of seconds.' >&2
    exit 2
fi
export LOG_INTERVAL_SECONDS="$interval"

snippet_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file="$snippet_dir/../docker-compose.yml"

docker compose -f "$compose_file" --profile pipeline up --detach --build app-hr app-billing
echo "Each app emits a new log every $interval seconds. Press Ctrl+C to stop watching."
echo 'The apps keep running. Stop them with the stop command in pulse-logs.txt.'
docker compose -f "$compose_file" logs --follow --tail 0 --timestamps app-hr app-billing
