#!/bin/sh
# @skyhook-implements NFR-004
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
    echo "Starting Evidentia requires Docker with the Compose plugin." >&2
    exit 1
fi

compose() {
    docker compose --env-file "$environment_file" \
        -f "$repository_root/infra/compose/compose.yaml" \
        -f "$repository_root/infra/compose/compose.dev.yaml" "$@"
}

compose config --quiet
compose up --build --detach
EVIDENTIA_ENV_FILE="$environment_file" "$repository_root/ci/local-runtime-check.sh"
