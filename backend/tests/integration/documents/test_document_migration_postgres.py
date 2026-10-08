"""Native PostgreSQL reversibility test for the documents migration branch.

@skyhook-implements REQ-001
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from backend.tests.integration.support import DisposablePostgresDatabase

pytestmark = pytest.mark.postgres
_REPOSITORY_ROOT = Path(__file__).parents[4]


def test_documents_branch_downgrades_without_touching_other_contexts(
    disposable_postgres_database: DisposablePostgresDatabase,
) -> None:
    """Prove rollback removes only the documents-owned namespace."""
    settings = disposable_postgres_database.settings
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(_REPOSITORY_ROOT / "backend" / "alembic.ini"),
            "-x",
            f"database_name={disposable_postgres_database.name}",
            "downgrade",
            "documents@base",
        ],
        cwd=_REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    password = None if settings.password is None else settings.password.get_secret_value()
    with (
        psycopg.connect(
            host=settings.host,
            port=settings.port,
            dbname=settings.name,
            user=settings.user,
            password=password,
            sslmode=settings.sslmode,
        ) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name IN "
            "('evidentia_access', 'evidentia_documents', 'evidentia_schemas') "
            "ORDER BY schema_name"
        )
        assert cursor.fetchall() == [("evidentia_access",), ("evidentia_schemas",)]
