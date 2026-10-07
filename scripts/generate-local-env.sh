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
    bootstrap_password=$(openssl rand -hex 24)
    session_secret=$(openssl rand -hex 32)
elif command -v python3 >/dev/null 2>&1; then
    database_password=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    bootstrap_password=$(python3 -c 'import secrets; print(secrets.token_hex(24))')
    session_secret=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
else
    echo "Generating local secrets requires openssl or python3." >&2
    exit 1
fi

umask 077
{
    echo "# Generated locally by scripts/generate-local-env.sh. Do not commit."
    echo "POSTGRES_DB=evidentia"
    echo "POSTGRES_USER=evidentia"
    echo "POSTGRES_PASSWORD=$database_password"
    echo "EVIDENTIA_DATABASE_PORT=5432"
    echo "EVIDENTIA_API_PORT=8000"
    echo "EVIDENTIA_WEB_PORT=3000"
    echo "EVIDENTIA_DATABASE__HOST=127.0.0.1"
    echo "EVIDENTIA_DATABASE__PORT=5432"
    echo "EVIDENTIA_DATABASE__NAME=evidentia"
    echo "EVIDENTIA_DATABASE__USER=evidentia"
    echo "EVIDENTIA_DATABASE__PASSWORD=$database_password"
    echo "EVIDENTIA_DATABASE__CONNECT_TIMEOUT_SECONDS=5"
    echo "EVIDENTIA_DATABASE__SSLMODE=prefer"
    echo "EVIDENTIA_DATABASE__APPLICATION_NAME=evidentia"
    echo 'EVIDENTIA_IDENTITY__BOOTSTRAP_LOGIN_IDENTIFIER=admin@localhost'
    echo 'EVIDENTIA_IDENTITY__BOOTSTRAP_DISPLAY_NAME="Local Administrator"'
    echo 'EVIDENTIA_IDENTITY__BOOTSTRAP_TENANT_SLUG=local'
    echo 'EVIDENTIA_IDENTITY__BOOTSTRAP_TENANT_NAME="Local Evidentia Workspace"'
    echo "EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD=$bootstrap_password"
    echo "EVIDENTIA_SESSION__SECRET=$session_secret"
    echo 'EVIDENTIA_SESSION__IDLE_TIMEOUT_SECONDS=1800'
    echo 'EVIDENTIA_SESSION__ABSOLUTE_TIMEOUT_SECONDS=43200'
    echo 'EVIDENTIA_SESSION__COOKIE_NAME=evidentia_session'
    echo 'EVIDENTIA_SESSION__COOKIE_SECURE=false'
    echo 'EVIDENTIA_SESSION__COOKIE_SAMESITE=lax'
} >"$temporary"
mv "$temporary" "$target"
trap - EXIT INT TERM

echo "Created owner-readable local environment file: $target"
