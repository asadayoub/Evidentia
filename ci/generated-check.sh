#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repository_root"
export UV_CACHE_DIR=${UV_CACHE_DIR:-"$repository_root/.uv-cache"}

uv lock --check
pnpm install --lockfile-only --frozen-lockfile
uv run python tools/check_generated_headers.py
