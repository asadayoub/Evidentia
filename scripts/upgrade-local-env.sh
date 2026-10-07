#!/bin/sh
# @skyhook-implements NFR-004
# @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
target=${EVIDENTIA_ENV_FILE:-"$repository_root/.env"}
temporary="$target.tmp.$$"

cleanup() {
    rm -f "$temporary"
}
trap cleanup EXIT INT TERM

if [ ! -f "$target" ] || [ -L "$target" ]; then
    echo "Upgrading local identity configuration requires a regular environment file: $target" >&2
    exit 1
fi

password_lines=$(grep -c '^POSTGRES_PASSWORD=' "$target" || true)
if [ "$password_lines" -ne 1 ]; then
    echo "Expected exactly one POSTGRES_PASSWORD entry in $target." >&2
    exit 1
fi
database_password=$(sed -n 's/^POSTGRES_PASSWORD=//p' "$target")
case "$database_password" in
    *[!0-9a-f]* | '')
        echo "POSTGRES_PASSWORD must be the generated 64-character lowercase hex secret." >&2
        exit 1
        ;;
esac
if [ "${#database_password}" -ne 64 ]; then
    echo "POSTGRES_PASSWORD must be the generated 64-character lowercase hex secret." >&2
    exit 1
fi

if command -v openssl >/dev/null 2>&1; then
    bootstrap_password=$(openssl rand -hex 24)
    session_secret=$(openssl rand -hex 32)
elif command -v python3 >/dev/null 2>&1; then
    bootstrap_password=$(python3 -c 'import secrets; print(secrets.token_hex(24))')
    session_secret=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
else
    echo "Generating local identity secrets requires openssl or python3." >&2
    exit 1
fi

has_key() {
    grep -q "^$1=" "$target"
}

missing=false
for key in \
    POSTGRES_DB \
    POSTGRES_USER \
    EVIDENTIA_DATABASE__HOST \
    EVIDENTIA_DATABASE__PORT \
    EVIDENTIA_DATABASE__NAME \
    EVIDENTIA_DATABASE__USER \
    EVIDENTIA_DATABASE__PASSWORD \
    EVIDENTIA_DATABASE__CONNECT_TIMEOUT_SECONDS \
    EVIDENTIA_DATABASE__SSLMODE \
    EVIDENTIA_DATABASE__APPLICATION_NAME \
    EVIDENTIA_IDENTITY__BOOTSTRAP_LOGIN_IDENTIFIER \
    EVIDENTIA_IDENTITY__BOOTSTRAP_DISPLAY_NAME \
    EVIDENTIA_IDENTITY__BOOTSTRAP_TENANT_SLUG \
    EVIDENTIA_IDENTITY__BOOTSTRAP_TENANT_NAME \
    EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD \
    EVIDENTIA_SESSION__SECRET \
    EVIDENTIA_SESSION__IDLE_TIMEOUT_SECONDS \
    EVIDENTIA_SESSION__ABSOLUTE_TIMEOUT_SECONDS \
    EVIDENTIA_SESSION__COOKIE_NAME \
    EVIDENTIA_SESSION__COOKIE_SECURE \
    EVIDENTIA_SESSION__COOKIE_SAMESITE
do
    if ! has_key "$key"; then
        missing=true
        break
    fi
done

if [ "$missing" = false ]; then
    chmod 600 "$target"
    echo "Local environment already contains the required identity configuration: $target"
    exit 0
fi

umask 077
cp "$target" "$temporary"
printf '\n%s\n' '# Added by scripts/upgrade-local-env.sh. Existing values were preserved.' >>"$temporary"

append_if_missing() {
    key=$1
    value=$2
    if ! has_key "$key"; then
        printf '%s=%s\n' "$key" "$value" >>"$temporary"
    fi
}

append_if_missing POSTGRES_DB evidentia
append_if_missing POSTGRES_USER evidentia
append_if_missing EVIDENTIA_DATABASE__HOST 127.0.0.1
append_if_missing EVIDENTIA_DATABASE__PORT 5432
append_if_missing EVIDENTIA_DATABASE__NAME evidentia
append_if_missing EVIDENTIA_DATABASE__USER evidentia
append_if_missing EVIDENTIA_DATABASE__PASSWORD "$database_password"
append_if_missing EVIDENTIA_DATABASE__CONNECT_TIMEOUT_SECONDS 5
append_if_missing EVIDENTIA_DATABASE__SSLMODE prefer
append_if_missing EVIDENTIA_DATABASE__APPLICATION_NAME evidentia
append_if_missing EVIDENTIA_IDENTITY__BOOTSTRAP_LOGIN_IDENTIFIER admin@localhost
append_if_missing EVIDENTIA_IDENTITY__BOOTSTRAP_DISPLAY_NAME '"Local Administrator"'
append_if_missing EVIDENTIA_IDENTITY__BOOTSTRAP_TENANT_SLUG local
append_if_missing EVIDENTIA_IDENTITY__BOOTSTRAP_TENANT_NAME '"Local Evidentia Workspace"'
append_if_missing EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD "$bootstrap_password"
append_if_missing EVIDENTIA_SESSION__SECRET "$session_secret"
append_if_missing EVIDENTIA_SESSION__IDLE_TIMEOUT_SECONDS 1800
append_if_missing EVIDENTIA_SESSION__ABSOLUTE_TIMEOUT_SECONDS 43200
append_if_missing EVIDENTIA_SESSION__COOKIE_NAME evidentia_session
append_if_missing EVIDENTIA_SESSION__COOKIE_SECURE false
append_if_missing EVIDENTIA_SESSION__COOKIE_SAMESITE lax

chmod 600 "$temporary"
mv "$temporary" "$target"
trap - EXIT INT TERM

echo "Added missing local identity configuration without replacing existing values: $target"
