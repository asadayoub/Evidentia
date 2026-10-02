#!/bin/sh
# @skyhook-implements NFR-004
# @skyhook-story STORY-009
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
target=${EVIDENTIA_ENV_FILE:-"$repository_root/.env"}
temporary="$target.tmp.$$"

cleanup() {
    rm -f "$temporary"
}
trap cleanup EXIT INT TERM

if [ -e "$target" ]; then
    echo "Refusing to overwrite existing environment file: $target" >&2
    exit 1
fi

if command -v openssl >/dev/null 2>&1; then
    database_password=$(openssl rand -hex 32)
elif command -v python3 >/dev/null 2>&1; then
    database_password=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
else
    echo "Generating local secrets requires openssl or python3." >&2
    exit 1
fi

umask 077
{
    echo "# Generated locally by scripts/generate-local-env.sh. Do not commit."
    echo "POSTGRES_PASSWORD=$database_password"
    echo "EVIDENTIA_DATABASE_PORT=5432"
    echo "EVIDENTIA_API_PORT=8000"
    echo "EVIDENTIA_WEB_PORT=3000"
} >"$temporary"
mv "$temporary" "$target"
trap - EXIT INT TERM

echo "Created owner-readable local environment file: $target"
