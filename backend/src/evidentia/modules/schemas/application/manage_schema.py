"""Authorized, persistence-independent schema lifecycle commands.

The caller owns the transaction around each command. This service never commits,
so publication insertion and draft advancement succeed or roll back together.

@skyhook-implements REQ-003
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story X51S43NTMRW5ASYSKJBF7FW845
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Protocol
from uuid import UUID

from evidentia.modules.schemas.application.publish_schema import (
    ArtifactKey,
    SchemaDraft,
    publish_schema,
)
from evidentia.modules.schemas.application.repositories import (
    DraftNotFoundError,
    DraftRevisionConflictError,
    SchemaRepository,
    StoredSchemaDraft,
    StoredSchemaPublication,
)
from evidentia.modules.schemas.domain.artifact_links import ArtifactBindings
from evidentia.modules.schemas.domain.definitions import FieldDefinition
from evidentia.modules.schemas.domain.identity import ReleaseLabel, SchemaId, SchemaVersion
from evidentia.modules.schemas.domain.modules import PublishedSchemaModule

SCHEMAS_READ = "schemas.read"
SCHEMAS_PUBLISH = "schemas.publish"
SCHEMAS_WRITE = "schemas.write"


class SchemaAuthorizationError(PermissionError):
    """Fail-closed authorization denial translated by an interface adapter.

    @skyhook-implements NFR-002
    @skyhook-implements NFR-008
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    def __init__(self, required_capability: str) -> None:
        self.required_capability = required_capability
        super().__init__("schema capability is required")


@dataclass(frozen=True, slots=True)
class SchemaCommandContext:
    """Schema-owned authority translated from an authenticated principal.

    @skyhook-implements NFR-002
    @skyhook-implements NFR-008
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    tenant_id: UUID
    actor_id: str
    capabilities: frozenset[str]
    correlation_id: str

    def __post_init__(self) -> None:
        if self.tenant_id.int == 0:
            raise ValueError("schema tenant identity cannot be nil")
        _require_identifier(self.actor_id, "actor")
        _require_identifier(self.correlation_id, "correlation")
        if not isinstance(self.capabilities, frozenset) or not all(
            isinstance(item, str) and item for item in self.capabilities
        ):
            raise ValueError("schema capabilities must be non-empty strings")


class SchemaArtifactCatalog(Protocol):
    """Resolve trusted artifact digests required by a draft publication.

    @skyhook-implements REQ-003
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    async def available_artifacts(
        self, tenant_id: UUID, draft: SchemaDraft
    ) -> Mapping[ArtifactKey, str]:
        """Return authoritative digests visible within the tenant boundary."""
        ...


@dataclass(frozen=True, slots=True)
class SchemaDraftContent:
    """Canonical replacement content accepted by lifecycle commands.

    Identity, target publication version, tenant, actor, and audit metadata are
    deliberately absent because the server derives them from durable state and
    trusted request context.

    @skyhook-implements REQ-003
    @skyhook-implements REQ-016
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    fields: tuple[FieldDefinition, ...] = ()
    modules: tuple[PublishedSchemaModule, ...] = ()
    release_label: ReleaseLabel | None = None
    artifacts: ArtifactBindings = field(default_factory=ArtifactBindings)


@dataclass(frozen=True, slots=True)
class PublishedSchemaDraft:
    """Atomic result of publication and advancement to the next draft revision.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    publication: StoredSchemaPublication
    next_draft: StoredSchemaDraft


class ManageSchemaLifecycle:
    """Authorize and coordinate tenant-scoped schema lifecycle operations.

    Create is intentionally not safe for blind transport retry until the API
    boundary supplies durable idempotency. Replacement and publication require
    the last observed draft revision. A successful publication advances that
    revision in the same caller-owned transaction, making a repeated command
    conflict instead of silently publishing a second version.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-implements NFR-002
    @skyhook-implements NFR-008
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    def __init__(
        self,
        repository: SchemaRepository,
        artifacts: SchemaArtifactCatalog,
    ) -> None:
        self._repository = repository
        self._artifacts = artifacts

    def authorize_read(self, context: SchemaCommandContext) -> None:
        """Validate schema read authority for mutation-free derived operations.

        @skyhook-implements NFR-002
        @skyhook-story STORY-018
        """
        _require(context, SCHEMAS_READ)

    async def create_draft(
        self,
        context: SchemaCommandContext,
        content: SchemaDraftContent,
    ) -> StoredSchemaDraft:
        """Create a server-identified version-one draft for the trusted tenant."""
        _require(context, SCHEMAS_WRITE)
        draft = _draft(SchemaId.new(), SchemaVersion(1), content)
        return await self._repository.create_draft(
            context.tenant_id, draft, actor_id=context.actor_id
        )

    async def get_draft(
        self,
        context: SchemaCommandContext,
        schema_id: SchemaId,
    ) -> StoredSchemaDraft | None:
        """Return one tenant-owned draft to an authorized reader."""
        _require(context, SCHEMAS_READ)
        return await self._repository.get_draft(context.tenant_id, schema_id)

    async def list_drafts(self, context: SchemaCommandContext) -> tuple[StoredSchemaDraft, ...]:
        """Return deterministic tenant-owned drafts to an authorized reader."""
        _require(context, SCHEMAS_READ)
        return await self._repository.list_drafts(context.tenant_id)

    async def replace_draft(
        self,
        context: SchemaCommandContext,
        schema_id: SchemaId,
        *,
        expected_revision: int,
        content: SchemaDraftContent,
    ) -> StoredSchemaDraft:
        """Replace canonical content only at the caller's observed revision."""
        _require(context, SCHEMAS_WRITE)
        tenant_id = context.tenant_id
        stored = await self._require_draft(tenant_id, schema_id)
        draft = _draft(schema_id, stored.draft.version, content)
        return await self._repository.update_draft(
            tenant_id,
            draft,
            expected_revision=expected_revision,
            actor_id=context.actor_id,
        )

    async def publish_draft(
        self,
        context: SchemaCommandContext,
        schema_id: SchemaId,
        *,
        expected_revision: int,
        acknowledgement: str | None = None,
    ) -> PublishedSchemaDraft:
        """Publish the next server-owned version and advance the mutable draft."""
        _require(context, SCHEMAS_PUBLISH)
        tenant_id = context.tenant_id
        stored = await self._require_draft(tenant_id, schema_id)
        if stored.revision != expected_revision:
            raise DraftRevisionConflictError("draft revision no longer matches")
        previous = await self._repository.get_latest_publication(tenant_id, schema_id)
        version = (
            SchemaVersion(1) if previous is None else previous.publication.schema.version.next()
        )
        candidate = replace(stored.draft, version=version)
        available_artifacts = await self._artifacts.available_artifacts(tenant_id, candidate)
        publication = publish_schema(
            candidate,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            available_artifacts=available_artifacts,
            previous=None if previous is None else previous.publication.schema,
            acknowledgement=acknowledgement,
        )
        persisted = await self._repository.add_publication(
            tenant_id,
            publication,
            previous_version=(None if previous is None else previous.publication.schema.version),
        )
        next_draft = await self._repository.update_draft(
            tenant_id,
            replace(candidate, version=version.next()),
            expected_revision=expected_revision,
            actor_id=context.actor_id,
        )
        return PublishedSchemaDraft(persisted, next_draft)

    async def get_publication(
        self,
        context: SchemaCommandContext,
        schema_id: SchemaId,
        version: SchemaVersion,
    ) -> StoredSchemaPublication | None:
        """Return an exact immutable tenant publication to an authorized reader."""
        _require(context, SCHEMAS_READ)
        return await self._repository.get_publication(context.tenant_id, schema_id, version)

    async def _require_draft(self, tenant_id: UUID, schema_id: SchemaId) -> StoredSchemaDraft:
        stored = await self._repository.get_draft(tenant_id, schema_id)
        if stored is None:
            raise DraftNotFoundError("tenant schema draft was not found")
        return stored


def _draft(
    schema_id: SchemaId,
    version: SchemaVersion,
    content: SchemaDraftContent,
) -> SchemaDraft:
    return SchemaDraft(
        schema_id=schema_id,
        version=version,
        fields=content.fields,
        modules=content.modules,
        release_label=content.release_label,
        artifacts=content.artifacts,
    )


def _require(context: SchemaCommandContext, capability: str) -> None:
    if capability not in context.capabilities:
        raise SchemaAuthorizationError(capability)


def _require_identifier(value: str, subject: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 255
        or any(character.isspace() for character in value)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"schema {subject} identity is invalid")
