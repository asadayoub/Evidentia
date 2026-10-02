#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repository_root"
export UV_CACHE_DIR=${UV_CACHE_DIR:-"$repository_root/.uv-cache"}

./ci/generated-check.sh
./ci/format-check.sh
./ci/lint.sh
./ci/type-check.sh
./ci/unit-test.sh
pnpm build
