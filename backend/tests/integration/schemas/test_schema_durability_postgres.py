"""Committed cross-session durability and isolation proof for schema storage.

@skyhook-implements REQ-003
@skyhook-implements REQ-005
@skyhook-implements REQ-006
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from backend.tests.integration.support import DisposablePostgresDatabase
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError

from evidentia.modules.schemas.application.publish_schema import SchemaDraft, publish_schema
from evidentia.modules.schemas.application.repositories import (
    DraftNotFoundError,
    PublicationAlreadyExistsError,
)
from evidentia.modules.schemas.domain.artifact_links import (
    ArtifactBindings,
    PublishedArtifactReference,
    SchemaArtifactKind,
)
from evidentia.modules.schemas.domain.definitions import FieldDefinition, ValueDefinition
from evidentia.modules.schemas.domain.field_types import StringType
from evidentia.modules.schemas.domain.identity import FieldKey, SchemaId, SchemaVersion
from evidentia.modules.schemas.infrastructure.database import (
    create_schema_engine,
    create_schema_session_factory,
)
from evidentia.modules.schemas.infrastructure.persistence import SchemaPublicationRecord
from evidentia.modules.schemas.infrastructure.repository import PostgresSchemaRepository

pytestmark = pytest.mark.postgres


async def _prove_durability(database: DisposablePostgresDatabase) -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    schema_id = SchemaId.new()
    published_at = datetime(2026, 10, 3, 18, 0, tzinfo=UTC)
    artifact = PublishedArtifactReference(
        artifact_id=str(uuid4()),
        version=SchemaVersion(7),
        kind=SchemaArtifactKind.EVIDENCE_EXPECTATION,
        content_sha256="b" * 64,
    )
    draft = SchemaDraft(
        schema_id=schema_id,
        version=SchemaVersion(1),
        fields=(
            FieldDefinition(
                FieldKey("invoice_number"),
                ValueDefinition.scalar(StringType(min_length=1, max_length=100)),
            ),
        ),
        artifacts=ArtifactBindings((artifact,)),
    )
    publication = publish_schema(
        draft,
        actor_id="publisher-committed",
        correlation_id="request-committed",
        available_artifacts={
            (artifact.artifact_id, artifact.version.value, artifact.kind.value): (
                artifact.content_sha256
            )
        },
        published_at=published_at,
    )

    first_engine = create_schema_engine(database.settings, purpose="durability-write")
    first_sessions = create_schema_session_factory(first_engine)
    try:
        async with first_sessions.begin() as session:
            repository = PostgresSchemaRepository(session)
            created_draft = await repository.create_draft(
                tenant_id, draft, actor_id="editor-committed"
            )
            created_publication = await repository.add_publication(
                tenant_id,
                publication,
                previous_version=None,
            )
    finally:
        await first_engine.dispose()

    second_engine = create_schema_engine(database.settings, purpose="durability-read")
    second_sessions = create_schema_session_factory(second_engine)
    try:
        async with second_sessions() as session:
            repository = PostgresSchemaRepository(session)
            loaded_draft = await repository.get_draft(tenant_id, schema_id)
            loaded_publication = await repository.get_publication(
                tenant_id, schema_id, SchemaVersion(1)
            )
            assert loaded_draft == created_draft
            assert loaded_publication == created_publication
            assert loaded_publication is not None
            assert loaded_publication.publication.content_sha256 == publication.content_sha256
            assert loaded_publication.publication.provenance == publication.provenance
            assert loaded_publication.artifacts[0].reference == artifact

            assert await repository.get_draft(other_tenant_id, schema_id) is None
            assert (
                await repository.get_publication(other_tenant_id, schema_id, SchemaVersion(1))
                is None
            )
            with pytest.raises(DraftNotFoundError):
                await repository.update_draft(
                    other_tenant_id,
                    draft,
                    expected_revision=1,
                    actor_id="other-tenant",
                )

        async with second_sessions.begin() as session:
            repository = PostgresSchemaRepository(session)
            with pytest.raises(PublicationAlreadyExistsError):
                await repository.add_publication(
                    tenant_id,
                    publication,
                    previous_version=None,
                )

        with pytest.raises(DBAPIError, match="published schema records are immutable"):
            async with second_sessions.begin() as session:
                await session.execute(
                    update(SchemaPublicationRecord)
                    .where(
                        SchemaPublicationRecord.tenant_id == tenant_id,
                        SchemaPublicationRecord.schema_id == UUID(schema_id.value),
                        SchemaPublicationRecord.version == 1,
                    )
                    .values(version=2, content_sha256="c" * 64)
                )
    finally:
        await second_engine.dispose()


def test_committed_schema_state_survives_fresh_database_sessions(
    disposable_postgres_database: DisposablePostgresDatabase,
) -> None:
    """Prove committed state, immutability, isolation, evidence, and teardown.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    asyncio.run(_prove_durability(disposable_postgres_database))
