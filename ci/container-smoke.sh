#!/bin/sh
# @skyhook-implements NFR-004
# @skyhook-implements NFR-006
# @skyhook-story STORY-009
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repository_root"

if ! command -v docker >/dev/null 2>&1; then
    echo "container smoke check requires Docker" >&2
    exit 1
fi

run_id="$$"
api_image="evidentia-api-smoke:$run_id"
worker_image="evidentia-worker-smoke:$run_id"
web_image="evidentia-web-smoke:$run_id"
api_container="evidentia-api-smoke-$run_id"
worker_container="evidentia-worker-smoke-$run_id"
web_container="evidentia-web-smoke-$run_id"

cleanup() {
    docker rm --force "$api_container" "$worker_container" "$web_container" >/dev/null 2>&1 || true
    docker image rm --force "$api_image" "$worker_image" "$web_image" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

wait_until_healthy() {
    container_name=$1
    attempts=0
    while [ "$attempts" -lt 30 ]; do
        status=$(docker inspect --format '{{.State.Health.Status}}' "$container_name")
        if [ "$status" = "healthy" ]; then
            return 0
        fi
        if [ "$status" = "unhealthy" ]; then
            docker logs "$container_name" >&2
            return 1
        fi
        attempts=$((attempts + 1))
        sleep 1
    done
    docker logs "$container_name" >&2
    echo "$container_name did not become healthy" >&2
    return 1
}

docker build --file infra/containers/backend.Dockerfile --target api --tag "$api_image" .
docker build --file infra/containers/backend.Dockerfile --target worker --tag "$worker_image" .
docker build --file infra/containers/web.Dockerfile --target runtime --tag "$web_image" .

docker run --detach --name "$api_container" --read-only --tmpfs /tmp "$api_image" >/dev/null
docker run --detach --name "$worker_container" --read-only --tmpfs /tmp "$worker_image" >/dev/null
docker run --detach --name "$web_container" --read-only \
    --tmpfs /tmp:uid=101,gid=101 "$web_image" >/dev/null

wait_until_healthy "$api_container"
wait_until_healthy "$worker_container"
wait_until_healthy "$web_container"

echo "API, worker, and web container smoke checks passed."
