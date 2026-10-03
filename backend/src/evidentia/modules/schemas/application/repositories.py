"""Persistence-independent ports for tenant-scoped schema storage.

@skyhook-implements REQ-003
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from evidentia.modules.schemas.application.publish_schema import SchemaDraft, SchemaPublication
from evidentia.modules.schemas.domain.artifact_links import PublishedArtifactReference
from evidentia.modules.schemas.domain.identity import SchemaId, SchemaVersion


class SchemaRepositoryError(RuntimeError):
    """Base failure exposed by schema persistence ports.

    @skyhook-implements REQ-003
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """


class DraftAlreadyExistsError(SchemaRepositoryError):
    """A tenant already owns a draft for the stable schema identity.

    @skyhook-implements REQ-003
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """


class DraftNotFoundError(SchemaRepositoryError):
    """No draft is visible under the supplied tenant and schema identity.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """


class DraftRevisionConflictError(SchemaRepositoryError):
    """A draft changed after the caller's expected revision.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """


class PublicationAlreadyExistsError(SchemaRepositoryError):
    """The tenant-scoped schema version was already published.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """


class StoredSchemaIntegrityError(SchemaRepositoryError):
    """Persisted snapshot evidence failed canonical validation.

    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """


@dataclass(frozen=True, slots=True)
class StoredSchemaDraft:
    """Tenant-scoped draft plus concurrency and audit metadata.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """

    tenant_id: UUID
    draft: SchemaDraft
    revision: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StoredArtifactReference:
    """Location-aware normalized artifact metadata for one publication.

    @skyhook-implements REQ-003
    @skyhook-implements REQ-005
    @skyhook-implements REQ-006
    @skyhook-implements NFR-001
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """

    binding_path: str
    reference: PublishedArtifactReference


@dataclass(frozen=True, slots=True)
class StoredSchemaPublication:
    """Tenant-scoped immutable publication and normalized artifact evidence.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """

    tenant_id: UUID
    publication: SchemaPublication
    previous_version: SchemaVersion | None
    artifacts: tuple[StoredArtifactReference, ...]


class SchemaRepository(Protocol):
    """Transaction-neutral schema repository contract.

    The caller owns the transaction boundary. Implementations may flush changes
    and use savepoints for error translation, but never commit implicitly.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """

    async def create_draft(
        self, tenant_id: UUID, draft: SchemaDraft, *, actor_id: str
    ) -> StoredSchemaDraft:
        """Create the tenant's first mutable draft revision."""
        ...

    async def get_draft(self, tenant_id: UUID, schema_id: SchemaId) -> StoredSchemaDraft | None:
        """Load a draft only when both tenant and schema identity match."""
        ...

    async def list_drafts(self, tenant_id: UUID) -> tuple[StoredSchemaDraft, ...]:
        """List drafts visible to exactly one tenant."""
        ...

    async def update_draft(
        self,
        tenant_id: UUID,
        draft: SchemaDraft,
        *,
        expected_revision: int,
        actor_id: str,
    ) -> StoredSchemaDraft:
        """Replace draft content only at the expected optimistic revision."""
        ...

    async def add_publication(
        self,
        tenant_id: UUID,
        publication: SchemaPublication,
        *,
        previous_version: SchemaVersion | None,
    ) -> StoredSchemaPublication:
        """Stage one publication and all artifact rows atomically."""
        ...

    async def get_publication(
        self, tenant_id: UUID, schema_id: SchemaId, version: SchemaVersion
    ) -> StoredSchemaPublication | None:
        """Load one exact immutable tenant-scoped publication."""
        ...
