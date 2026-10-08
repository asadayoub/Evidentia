"""Native PostgreSQL verification for the schemas module migration.

These tests are opt-in because ordinary unit runs must not mutate a developer's
database. The inserted publication is always rolled back.

@skyhook-implements REQ-003
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from evidentia.config.settings import load_api_settings

pytestmark = pytest.mark.postgres

_REPOSITORY_ROOT = Path(__file__).parents[4]


def _connection() -> psycopg.Connection[tuple[object, ...]]:
    settings = load_api_settings(_REPOSITORY_ROOT / ".env").database
    password = None if settings.password is None else settings.password.get_secret_value()
    return psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=settings.name,
        user=settings.user,
        password=password,
        connect_timeout=max(1, int(settings.connect_timeout_seconds)),
        sslmode=settings.sslmode,
        application_name=f"{settings.application_name}-migration-test",
    )


def test_migration_created_only_the_owned_schema_tables() -> None:
    """Verify the live catalog reflects the module ownership boundary.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'evidentia_schemas'
            ORDER BY table_name
            """
        )
        assert [row[0] for row in cursor.fetchall()] == [
            "schema_command_receipts",
            "schema_drafts",
            "schema_publication_artifacts",
            "schema_publications",
        ]


def test_published_snapshot_rejects_update_without_leaving_test_data() -> None:
    """Prove database-level immutability independently of repository code.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    tenant_id = uuid4()
    schema_id = uuid4()
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO evidentia_schemas.schema_publications (
                tenant_id, schema_id, version, previous_version, release_label,
                snapshot_format, snapshot_format_version, snapshot, content_sha256,
                compatibility_level, compatibility, actor_id, correlation_id,
                acknowledgement, published_at
            ) VALUES (
                %s, %s, 1, NULL, NULL,
                'evidentia.schema', 1, %s, %s,
                NULL, NULL, 'migration-test', 'migration-test',
                NULL, CURRENT_TIMESTAMP
            )
            """,
            (tenant_id, schema_id, Jsonb({"fields": []}), "0" * 64),
        )
        with pytest.raises(
            psycopg.errors.ObjectNotInPrerequisiteState,
            match="published schema records are immutable",
        ):
            cursor.execute(
                """
                UPDATE evidentia_schemas.schema_publications
                SET release_label = 'changed'
                WHERE tenant_id = %s AND schema_id = %s AND version = 1
                """,
                (tenant_id, schema_id),
            )
        connection.rollback()
