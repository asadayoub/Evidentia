"""Application-contract tests for authorized schema lifecycle commands.

@skyhook-implements REQ-003
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements NFR-008
@skyhook-story X51S43NTMRW5ASYSKJBF7FW845
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from evidentia.modules.schemas.application.publish_schema import (
    ArtifactKey,
    SchemaDraft,
    SchemaPublication,
)
from evidentia.modules.schemas.application.repositories import (
    DraftAlreadyExistsError,
    DraftNotFoundError,
    DraftRevisionConflictError,
    PublicationAlreadyExistsError,
    SchemaRepository,
    StoredSchemaDraft,
    StoredSchemaPublication,
)
from evidentia.modules.schemas.public import (
    SCHEMAS_PUBLISH,
    SCHEMAS_READ,
    SCHEMAS_WRITE,
    FieldDefinition,
    FieldKey,
    ManageSchemaLifecycle,
    SchemaAuthorizationError,
    SchemaCommandContext,
    SchemaDraftContent,
    SchemaId,
    SchemaVersion,
    StringType,
    ValueDefinition,
)

TENANT_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
OTHER_TENANT_ID = UUID("223e4567-e89b-12d3-a456-426614174000")
OPERATOR_ID = "323e4567-e89b-12d3-a456-426614174000"
NOW = datetime(2026, 10, 7, tzinfo=UTC)


class MemorySchemaRepository:
    """Minimal transaction-like repository fake for lifecycle contract tests."""

    def __init__(self) -> None:
        self.drafts: dict[tuple[UUID, SchemaId], StoredSchemaDraft] = {}
        self.publications: dict[tuple[UUID, SchemaId, SchemaVersion], StoredSchemaPublication] = {}

    async def create_draft(
        self, tenant_id: UUID, draft: SchemaDraft, *, actor_id: str
    ) -> StoredSchemaDraft:
        key = (tenant_id, draft.schema_id)
        if key in self.drafts:
            raise DraftAlreadyExistsError
        stored = StoredSchemaDraft(tenant_id, draft, 1, actor_id, actor_id, NOW, NOW)
        self.drafts[key] = stored
        return stored

    async def get_draft(self, tenant_id: UUID, schema_id: SchemaId) -> StoredSchemaDraft | None:
        return self.drafts.get((tenant_id, schema_id))

    async def list_drafts(self, tenant_id: UUID) -> tuple[StoredSchemaDraft, ...]:
        return tuple(
            item
            for (item_tenant_id, _), item in sorted(
                self.drafts.items(), key=lambda entry: entry[0][1].value
            )
            if item_tenant_id == tenant_id
        )

    async def update_draft(
        self,
        tenant_id: UUID,
        draft: SchemaDraft,
        *,
        expected_revision: int,
        actor_id: str,
    ) -> StoredSchemaDraft:
        key = (tenant_id, draft.schema_id)
        current = self.drafts.get(key)
        if current is None:
            raise DraftNotFoundError
        if current.revision != expected_revision:
            raise DraftRevisionConflictError
        stored = replace(
            current,
            draft=draft,
            revision=current.revision + 1,
            updated_by=actor_id,
        )
        self.drafts[key] = stored
        return stored

    async def add_publication(
        self,
        tenant_id: UUID,
        publication: SchemaPublication,
        *,
        previous_version: SchemaVersion | None,
    ) -> StoredSchemaPublication:
        key = (tenant_id, publication.schema.schema_id, publication.schema.version)
        if key in self.publications:
            raise PublicationAlreadyExistsError
        stored = StoredSchemaPublication(tenant_id, publication, previous_version, ())
        self.publications[key] = stored
        return stored

    async def get_publication(
        self, tenant_id: UUID, schema_id: SchemaId, version: SchemaVersion
    ) -> StoredSchemaPublication | None:
        return self.publications.get((tenant_id, schema_id, version))

    async def get_latest_publication(
        self, tenant_id: UUID, schema_id: SchemaId
    ) -> StoredSchemaPublication | None:
        matches = [
            item
            for (item_tenant_id, item_schema_id, _), item in self.publications.items()
            if item_tenant_id == tenant_id and item_schema_id == schema_id
        ]
        return max(matches, key=lambda item: item.publication.schema.version.value, default=None)


class EmptyArtifactCatalog:
    """Trusted catalog with no published artifacts."""

    async def available_artifacts(
        self, tenant_id: UUID, draft: SchemaDraft
    ) -> Mapping[ArtifactKey, str]:
        assert tenant_id == TENANT_ID
        assert isinstance(draft, SchemaDraft)
        return {}


def _context(*capabilities: str, tenant_id: UUID = TENANT_ID) -> SchemaCommandContext:
    return SchemaCommandContext(
        tenant_id=tenant_id,
        actor_id=OPERATOR_ID,
        capabilities=frozenset(capabilities),
        correlation_id="request-1",
    )


def _content(field: str) -> SchemaDraftContent:
    return SchemaDraftContent(
        fields=(FieldDefinition(FieldKey(field), ValueDefinition.scalar(StringType())),)
    )


async def _create_uses_trusted_scope_and_server_owned_identity() -> None:
    repository = MemorySchemaRepository()
    service = ManageSchemaLifecycle(repository, EmptyArtifactCatalog())

    created = await service.create_draft(_context(SCHEMAS_WRITE), _content("reference"))

    assert created.tenant_id == TENANT_ID
    assert created.draft.version == SchemaVersion(1)
    assert created.created_by == OPERATOR_ID
    assert UUID(created.draft.schema_id.value)
    assert repository.drafts[(TENANT_ID, created.draft.schema_id)] == created


async def _capabilities_are_separate_and_fail_closed() -> None:
    service = ManageSchemaLifecycle(MemorySchemaRepository(), EmptyArtifactCatalog())

    with pytest.raises(SchemaAuthorizationError):
        await service.create_draft(_context(SCHEMAS_READ), _content("reference"))


async def _replace_is_canonical_and_revision_guarded() -> None:
    repository = MemorySchemaRepository()
    service = ManageSchemaLifecycle(repository, EmptyArtifactCatalog())
    created = await service.create_draft(_context(SCHEMAS_WRITE), _content("old"))

    replaced = await service.replace_draft(
        _context(SCHEMAS_WRITE),
        created.draft.schema_id,
        expected_revision=1,
        content=_content("replacement"),
    )

    assert replaced.revision == 2
    assert replaced.draft.schema_id == created.draft.schema_id
    assert replaced.draft.version == SchemaVersion(1)
    assert replaced.draft.fields[0].key == FieldKey("replacement")
    with pytest.raises(DraftRevisionConflictError):
        await service.replace_draft(
            _context(SCHEMAS_WRITE),
            created.draft.schema_id,
            expected_revision=1,
            content=_content("stale"),
        )


async def _publish_sequences_versions_and_makes_retries_conflict() -> None:
    repository = MemorySchemaRepository()
    service = ManageSchemaLifecycle(repository, EmptyArtifactCatalog())
    created = await service.create_draft(_context(SCHEMAS_WRITE), _content("legacy"))

    first = await service.publish_draft(
        _context(SCHEMAS_PUBLISH), created.draft.schema_id, expected_revision=1
    )

    assert first.publication.publication.schema.version == SchemaVersion(1)
    assert first.next_draft.draft.version == SchemaVersion(2)
    assert first.next_draft.revision == 2
    assert first.publication.publication.provenance.actor_id == OPERATOR_ID
    assert first.publication.publication.provenance.correlation_id == "request-1"
    with pytest.raises(DraftRevisionConflictError):
        await service.publish_draft(
            _context(SCHEMAS_PUBLISH), created.draft.schema_id, expected_revision=1
        )

    replacement = await service.replace_draft(
        _context(SCHEMAS_WRITE),
        created.draft.schema_id,
        expected_revision=2,
        content=_content("replacement"),
    )
    with pytest.raises(ValueError, match="requires acknowledgement"):
        await service.publish_draft(
            _context(SCHEMAS_PUBLISH),
            created.draft.schema_id,
            expected_revision=replacement.revision,
        )

    second = await service.publish_draft(
        _context(SCHEMAS_PUBLISH),
        created.draft.schema_id,
        expected_revision=replacement.revision,
        acknowledgement="Reviewed field replacement",
    )
    assert second.publication.previous_version == SchemaVersion(1)
    assert second.publication.publication.schema.version == SchemaVersion(2)
    assert second.next_draft.draft.version == SchemaVersion(3)


async def _reads_do_not_cross_the_trusted_tenant_boundary() -> None:
    repository: SchemaRepository = MemorySchemaRepository()
    service = ManageSchemaLifecycle(repository, EmptyArtifactCatalog())
    created = await service.create_draft(_context(SCHEMAS_WRITE), _content("reference"))

    visible = await service.get_draft(_context(SCHEMAS_READ), created.draft.schema_id)
    hidden = await service.get_draft(
        _context(SCHEMAS_READ, tenant_id=OTHER_TENANT_ID), created.draft.schema_id
    )

    assert visible == created
    assert hidden is None


def test_create_uses_trusted_scope_and_server_owned_identity() -> None:
    asyncio.run(_create_uses_trusted_scope_and_server_owned_identity())


def test_capabilities_are_separate_and_fail_closed() -> None:
    asyncio.run(_capabilities_are_separate_and_fail_closed())


def test_replace_is_canonical_and_revision_guarded() -> None:
    asyncio.run(_replace_is_canonical_and_revision_guarded())


def test_publish_sequences_versions_and_makes_retries_conflict() -> None:
    asyncio.run(_publish_sequences_versions_and_makes_retries_conflict())


def test_reads_do_not_cross_the_trusted_tenant_boundary() -> None:
    asyncio.run(_reads_do_not_cross_the_trusted_tenant_boundary())
