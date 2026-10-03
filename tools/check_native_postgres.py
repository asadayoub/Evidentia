"""Non-destructive readiness check for the native PostgreSQL workflow.

@skyhook-implements NFR-004
@skyhook-implements NFR-006
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PREFIX = "EVIDENTIA_DATABASE__"
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
GENERATED_SECRET = re.compile(r"^[0-9a-f]{64}$")


def _read_environment(path: Path) -> dict[str, str]:
    """Read simple dotenv assignments without executing their contents."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid environment assignment on line {number}")
        key, value = line.split("=", 1)
        if not key or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in key
        ):
            raise ValueError(f"invalid environment key on line {number}")
        values[key] = value
    return values


def _setting(values: dict[str, str], name: str, default: str) -> str:
    """Prefer the process environment over the local environment file."""
    return os.environ.get(f"{PREFIX}{name}", values.get(f"{PREFIX}{name}", default))


def _bootstrap(
    values: dict[str, str], host: str, port: str, name: str, user: str, password: str
) -> int:
    """Create the dedicated local role and database without replacing existing data."""
    if IDENTIFIER.fullmatch(name) is None or IDENTIFIER.fullmatch(user) is None:
        print(
            "Native database and role names must be lower-snake-case identifiers.", file=sys.stderr
        )
        return 2
    if GENERATED_SECRET.fullmatch(password) is None:
        print(
            "Run 'make local-init' to generate the required 64-character local secret.",
            file=sys.stderr,
        )
        return 2
    psql = shutil.which("psql")
    if psql is None:
        print("Native PostgreSQL initialization requires psql on PATH.", file=sys.stderr)
        return 2
    escaped_password = password.replace("'", "''")
    sql = f"""
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', '{user}', '{escaped_password}')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{user}') \\gexec
ALTER ROLE "{user}" LOGIN PASSWORD '{escaped_password}';
SELECT format('CREATE DATABASE %I OWNER %I', '{name}', '{user}')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '{name}') \\gexec
"""
    result = subprocess.run(
        [
            psql,
            "--host",
            host,
            "--port",
            port,
            "--dbname",
            "postgres",
            "--no-password",
            "--set",
            "ON_ERROR_STOP=1",
        ],
        check=False,
        input=sql,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Could not initialize the dedicated Evidentia role and database.", file=sys.stderr)
        return 1
    print(f"Native PostgreSQL initialized: database {name}, role {user}.")
    return 0


def _main() -> int:
    """Verify server readiness and authenticated application connectivity."""
    root = Path(__file__).resolve().parents[1]
    env_path = Path(os.environ.get("EVIDENTIA_ENV_FILE", root / ".env"))
    try:
        values = _read_environment(env_path)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Invalid Evidentia environment file: {error}", file=sys.stderr)
        return 2

    host = _setting(values, "HOST", "127.0.0.1")
    port = _setting(values, "PORT", values.get("EVIDENTIA_DATABASE_PORT", "5432"))
    name = _setting(values, "NAME", "evidentia")
    user = _setting(values, "USER", "evidentia")
    password = _setting(values, "PASSWORD", values.get("POSTGRES_PASSWORD", ""))
    timeout = _setting(values, "CONNECT_TIMEOUT_SECONDS", "5")
    sslmode = _setting(values, "SSLMODE", "prefer")
    application_name = _setting(values, "APPLICATION_NAME", "evidentia-readiness")

    if "--bootstrap" in sys.argv[1:]:
        bootstrap_result = _bootstrap(values, host, port, name, user, password)
        if bootstrap_result != 0:
            return bootstrap_result
    elif sys.argv[1:]:
        print("Usage: check_native_postgres.py [--bootstrap]", file=sys.stderr)
        return 2

    pg_isready = shutil.which("pg_isready")
    psql = shutil.which("psql")
    if pg_isready is None or psql is None:
        print(
            "Native PostgreSQL verification requires pg_isready and psql on PATH.", file=sys.stderr
        )
        return 2

    ready = subprocess.run(
        [pg_isready, "--host", host, "--port", port, "--dbname", name, "--username", user],
        check=False,
        capture_output=True,
        text=True,
    )
    if ready.returncode != 0:
        print(f"PostgreSQL is not accepting connections at {host}:{port}.", file=sys.stderr)
        return 1

    process_environment = os.environ.copy()
    process_environment["PGPASSWORD"] = password
    result = subprocess.run(
        [
            psql,
            "--host",
            host,
            "--port",
            port,
            "--dbname",
            name,
            "--username",
            user,
            "--no-password",
            "--set",
            "ON_ERROR_STOP=1",
            "--tuples-only",
            "--command",
            "SELECT current_setting('server_version_num')::integer / 10000, "
            "current_database(), current_user;",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **process_environment,
            "PGCONNECT_TIMEOUT": timeout,
            "PGSSLMODE": sslmode,
            "PGAPPNAME": application_name,
        },
    )
    if result.returncode != 0:
        print(
            "PostgreSQL accepted the socket but rejected the configured Evidentia connection.",
            file=sys.stderr,
        )
        return 1
    columns = [column.strip() for column in result.stdout.strip().split("|")]
    if len(columns) != 3 or columns[0] != "16" or columns[1:] != [name, user]:
        print(
            "PostgreSQL connection does not match the supported major, database, or role.",
            file=sys.stderr,
        )
        return 1
    print(f"Native PostgreSQL is ready: major 16, database {name}, role {user}, {host}:{port}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
