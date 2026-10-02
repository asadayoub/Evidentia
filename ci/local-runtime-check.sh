#!/bin/sh
# @skyhook-implements REQ-014
# @skyhook-implements NFR-006
# @skyhook-story STORY-009
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
environment_file=${EVIDENTIA_ENV_FILE:-"$repository_root/.env"}

if [ ! -f "$environment_file" ]; then
    echo "Missing $environment_file. Run 'make local-init' first." >&2
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    echo "Verifying Evidentia requires Docker with the Compose plugin." >&2
    exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
    echo "Verifying Evidentia requires curl." >&2
    exit 1
fi

compose() {
    docker compose --env-file "$environment_file" \
        -f "$repository_root/infra/compose/compose.yaml" \
        -f "$repository_root/infra/compose/compose.dev.yaml" "$@"
}

compose config --quiet
attempts=0
while [ "$attempts" -lt 90 ]; do
    api_address=$(compose port api 8000 2>/dev/null || true)
    web_address=$(compose port web 8080 2>/dev/null || true)
    if [ -n "$api_address" ] && [ -n "$web_address" ] \
        && compose exec -T database pg_isready --dbname=evidentia --username=evidentia \
            >/dev/null 2>&1 \
        && compose exec -T worker python -c \
            "from evidentia.entrypoints.worker import worker_probe; assert worker_probe()['status'] == 'ok'" \
            >/dev/null 2>&1 \
        && curl --fail --silent --show-error "http://$api_address/health/live" >/dev/null \
        && curl --fail --silent --show-error "http://$api_address/health/ready" >/dev/null \
        && curl --fail --silent --show-error "http://$web_address/health/live" >/dev/null; then
        echo "Evidentia local runtime is ready: database, API, worker, and web checks passed."
        exit 0
    fi
    attempts=$((attempts + 1))
    sleep 2
done

compose ps >&2
echo "Evidentia local runtime did not become ready within 180 seconds." >&2
exit 1
