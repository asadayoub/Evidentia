"""Native PostgreSQL behavior tests for tenant-scoped schema repositories.

All writes run below an outer transaction and are rolled back.

@skyhook-implements REQ-003
@skyhook-implements REQ-005
@skyhook-implements REQ-006
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from evidentia.config.settings import load_api_settings
from evidentia.modules.schemas.application.publish_schema import SchemaDraft, publish_schema
from evidentia.modules.schemas.application.repositories import (
    DraftAlreadyExistsError,
    DraftNotFoundError,
    DraftRevisionConflictError,
    PublicationAlreadyExistsError,
    SchemaRepository,
)
from evidentia.modules.schemas.domain.artifact_links import (
    ArtifactBindings,
    PublishedArtifactReference,
    SchemaArtifactKind,
)
from evidentia.modules.schemas.domain.definitions import FieldDefinition, ValueDefinition
from evidentia.modules.schemas.domain.field_types import StringType
from evidentia.modules.schemas.domain.identity import FieldKey, SchemaId, SchemaVersion
from evidentia.modules.schemas.infrastructure.database import create_schema_engine
from evidentia.modules.schemas.infrastructure.repository import PostgresSchemaRepository

pytestmark = pytest.mark.postgres

_REPOSITORY_ROOT = Path(__file__).parents[4]


def _draft(schema_id: SchemaId, *, artifact: PublishedArtifactReference) -> SchemaDraft:
    return SchemaDraft(
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


async def _exercise_repository() -> None:
    settings = load_api_settings(_REPOSITORY_ROOT / ".env").database
    engine = create_schema_engine(settings, purpose="repository-test")
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    schema_id = SchemaId.new()
    artifact = PublishedArtifactReference(
        artifact_id=str(uuid4()),
        version=SchemaVersion(3),
        kind=SchemaArtifactKind.VALIDATION_RULES,
        content_sha256="a" * 64,
    )
    draft = _draft(schema_id, artifact=artifact)

    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        repository: SchemaRepository = PostgresSchemaRepository(session)
        try:
            created = await repository.create_draft(tenant_id, draft, actor_id="editor-1")
            assert created.revision == 1
            assert await repository.list_drafts(tenant_id) == (created,)
            with pytest.raises(DraftAlreadyExistsError):
                await repository.create_draft(tenant_id, draft, actor_id="editor-2")
            assert await repository.get_draft(other_tenant_id, schema_id) is None
            assert await repository.list_drafts(other_tenant_id) == ()

            with pytest.raises(DraftNotFoundError):
                await repository.update_draft(
                    other_tenant_id,
                    draft,
                    expected_revision=1,
                    actor_id="intruder",
                )

            updated = await repository.update_draft(
                tenant_id,
                draft,
                expected_revision=1,
                actor_id="editor-2",
            )
            assert updated.revision == 2
            assert updated.updated_by == "editor-2"
            with pytest.raises(DraftRevisionConflictError):
                await repository.update_draft(
                    tenant_id,
                    draft,
                    expected_revision=1,
                    actor_id="stale-editor",
                )

            publication = publish_schema(
                draft,
                actor_id="publisher-1",
                correlation_id="request-1",
                available_artifacts={
                    (
                        artifact.artifact_id,
                        artifact.version.value,
                        artifact.kind.value,
                    ): artifact.content_sha256
                },
            )
            stored = await repository.add_publication(
                tenant_id,
                publication,
                previous_version=None,
            )
            assert stored.artifacts[0].binding_path == "$"
            assert stored.artifacts[0].reference == artifact
            assert (
                await repository.get_publication(other_tenant_id, schema_id, SchemaVersion(1))
                is None
            )

            loaded = await repository.get_publication(tenant_id, schema_id, SchemaVersion(1))
            assert loaded == stored
            with pytest.raises(PublicationAlreadyExistsError):
                await repository.add_publication(
                    tenant_id,
                    publication,
                    previous_version=None,
                )
            assert (
                await repository.get_publication(tenant_id, schema_id, SchemaVersion(1)) == stored
            )

            second_draft = SchemaDraft(
                schema_id=schema_id,
                version=SchemaVersion(2),
                fields=(
                    *draft.fields,
                    FieldDefinition(
                        FieldKey("purchase_order"),
                        ValueDefinition.scalar(StringType(max_length=100)),
                    ),
                ),
                artifacts=draft.artifacts,
            )
            second_publication = publish_schema(
                second_draft,
                actor_id="publisher-2",
                correlation_id="request-2",
                available_artifacts={
                    (
                        artifact.artifact_id,
                        artifact.version.value,
                        artifact.kind.value,
                    ): artifact.content_sha256
                },
                previous=publication.schema,
            )
            stored_second = await repository.add_publication(
                tenant_id,
                second_publication,
                previous_version=SchemaVersion(1),
            )
            assert stored_second.publication.compatibility is not None
            assert (
                await repository.get_publication(tenant_id, schema_id, SchemaVersion(2))
                == stored_second
            )
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()
    await engine.dispose()


def test_repository_enforces_tenant_concurrency_and_publication_invariants() -> None:
    """Exercise draft and publication operations against PostgreSQL.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    asyncio.run(_exercise_repository())
