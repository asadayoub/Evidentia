#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repository_root"
export UV_CACHE_DIR=${UV_CACHE_DIR:-"$repository_root/.uv-cache"}

./ci/generated-check.sh
pnpm --filter @evidentia/web exec vitest run src/App.test.tsx
uv run pytest --postgres backend/tests/api/access/test_access_api_postgres.py
