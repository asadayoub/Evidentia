#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repository_root"
export UV_CACHE_DIR=${UV_CACHE_DIR:-"$repository_root/.uv-cache"}

uv run ruff check .
PYTHONPATH=backend/src uv run lint-imports --no-cache
uv run python tools/check_architecture.py
pnpm lint
