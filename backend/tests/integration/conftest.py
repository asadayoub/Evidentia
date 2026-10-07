"""Disposable native PostgreSQL database support for integration tests.

@skyhook-implements NFR-004
@skyhook-implements NFR-008
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import getpass
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from backend.tests.integration.support import DisposablePostgresDatabase
from psycopg import sql

from evidentia.config.settings import load_api_settings

_REPOSITORY_ROOT = Path(__file__).parents[3]
_TEST_DATABASE = re.compile(r"^evidentia_test_[0-9a-f]{16}$")


def _admin_connection(admin_user: str) -> psycopg.Connection[tuple[object, ...]]:
    return psycopg.connect(dbname="postgres", user=admin_user, autocommit=True)


def _drop_database(admin_user: str, database_name: str) -> None:
    if _TEST_DATABASE.fullmatch(database_name) is None:
        raise ValueError("refusing to drop a database outside the disposable test namespace")
    with _admin_connection(admin_user) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (database_name,),
        )
        cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name)))
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,))
        if cursor.fetchone() is not None:
            raise RuntimeError("disposable PostgreSQL database teardown did not complete")


@pytest.fixture
def disposable_postgres_database(
    request: pytest.FixtureRequest,
) -> Iterator[DisposablePostgresDatabase]:
    """Create, migrate, yield, and reliably remove an isolated database.

    @skyhook-implements NFR-004
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    configured_admin = request.config.getoption("--postgres-admin-user")
    admin_user = configured_admin if isinstance(configured_admin, str) else getpass.getuser()
    database_name = f"evidentia_test_{uuid4().hex[:16]}"
    base_settings = load_api_settings(_REPOSITORY_ROOT / ".env").database
    with _admin_connection(admin_user) as connection, connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                sql.Identifier(database_name), sql.Identifier(base_settings.user)
            )
        )
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(_REPOSITORY_ROOT / "backend" / "alembic.ini"),
                "-x",
                f"database_name={database_name}",
                "upgrade",
                "heads",
            ],
            cwd=_REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        yield DisposablePostgresDatabase(
            database_name,
            base_settings.model_copy(update={"name": database_name}),
        )
    finally:
        _drop_database(admin_user, database_name)
