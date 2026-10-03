"""Async PostgreSQL adapter for tenant-scoped schema repository ports.

@skyhook-implements REQ-003
@skyhook-implements REQ-005
@skyhook-implements REQ-006
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from evidentia.modules.schemas.application.interchange import (
    DRAFT_INTERCHANGE_VERSION,
    INTERCHANGE_FORMAT,
    INTERCHANGE_VERSION,
    export_schema,
    export_schema_draft,
    import_schema,
    import_schema_draft,
)
from evidentia.modules.schemas.application.publish_schema import (
    PublicationProvenance,
    SchemaDraft,
    SchemaPublication,
    schema_content_sha256,
)
from evidentia.modules.schemas.application.repositories import (
    DraftAlreadyExistsError,
    DraftNotFoundError,
    DraftRevisionConflictError,
    PublicationAlreadyExistsError,
    StoredArtifactReference,
    StoredSchemaDraft,
    StoredSchemaIntegrityError,
    StoredSchemaPublication,
)
from evidentia.modules.schemas.domain.artifact_links import (
    ArtifactBindings,
    PublishedArtifactReference,
    SchemaArtifactKind,
)
from evidentia.modules.schemas.domain.compatibility import (
    CompatibilityLevel,
    CompatibilityReport,
    SchemaChange,
    SchemaChangeCode,
)
from evidentia.modules.schemas.domain.definitions import FieldDefinition, ValueDefinition
from evidentia.modules.schemas.domain.identity import FieldPath, SchemaId, SchemaVersion
from evidentia.modules.schemas.domain.modules import PublishedSchemaModule, PublishedSchemaVersion
from evidentia.modules.schemas.infrastructure.persistence import (
    SchemaDraftRecord,
    SchemaPublicationArtifactRecord,
    SchemaPublicationRecord,
)


class PostgresSchemaRepository:
    """SQLAlchemy implementation that never commits its caller-owned transaction.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_draft(
        self, tenant_id: UUID, draft: SchemaDraft, *, actor_id: str
    ) -> StoredSchemaDraft:
        """Insert a new tenant draft and translate identity collisions.

        @skyhook-implements REQ-003
        @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
        """
        _require_actor(actor_id)
        record = SchemaDraftRecord(
            tenant_id=tenant_id,
            schema_id=UUID(draft.schema_id.value),
            revision=1,
            draft_format_version=DRAFT_INTERCHANGE_VERSION,
            release_label=None if draft.release_label is None else draft.release_label.value,
            definition=_json_object(export_schema_draft(draft)),
            created_by=actor_id,
            updated_by=actor_id,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(record)
                await self._session.flush()
        except IntegrityError as error:
            if _constraint_name(error) == "pk_schema_drafts":
                raise DraftAlreadyExistsError("tenant schema draft already exists") from error
            raise
        await self._session.refresh(record)
        return _stored_draft(record)

    async def get_draft(self, tenant_id: UUID, schema_id: SchemaId) -> StoredSchemaDraft | None:
        """Load a draft without exposing another tenant's matching identity.

        @skyhook-implements REQ-003
        @skyhook-implements NFR-008
        @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
        """
        record = await self._session.scalar(
            select(SchemaDraftRecord).where(
                SchemaDraftRecord.tenant_id == tenant_id,
                SchemaDraftRecord.schema_id == UUID(schema_id.value),
            )
        )
        return None if record is None else _stored_draft(record)

    async def list_drafts(self, tenant_id: UUID) -> tuple[StoredSchemaDraft, ...]:
        """Return a deterministic tenant-only draft listing.

        @skyhook-implements REQ-003
        @skyhook-implements NFR-008
        @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
        """
        records = (
            await self._session.scalars(
                select(SchemaDraftRecord)
                .where(SchemaDraftRecord.tenant_id == tenant_id)
                .order_by(SchemaDraftRecord.schema_id)
            )
        ).all()
        return tuple(_stored_draft(record) for record in records)

    async def update_draft(
        self,
        tenant_id: UUID,
        draft: SchemaDraft,
        *,
        expected_revision: int,
        actor_id: str,
    ) -> StoredSchemaDraft:
        """Atomically compare and increment the draft revision.

        @skyhook-implements REQ-003
        @skyhook-implements NFR-001
        @skyhook-implements NFR-008
        @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
        """
        if expected_revision < 1:
            raise ValueError("expected draft revision must be positive")
        _require_actor(actor_id)
        schema_id = UUID(draft.schema_id.value)
        result = await self._session.execute(
            update(SchemaDraftRecord)
            .where(
                SchemaDraftRecord.tenant_id == tenant_id,
                SchemaDraftRecord.schema_id == schema_id,
                SchemaDraftRecord.revision == expected_revision,
            )
            .values(
                revision=SchemaDraftRecord.revision + 1,
                draft_format_version=DRAFT_INTERCHANGE_VERSION,
                release_label=None if draft.release_label is None else draft.release_label.value,
                definition=_json_object(export_schema_draft(draft)),
                updated_by=actor_id,
                updated_at=func.now(),
            )
            .returning(SchemaDraftRecord)
        )
        record = result.scalar_one_or_none()
        if record is not None:
            return _stored_draft(record)
        exists = await self._session.scalar(
            select(SchemaDraftRecord.schema_id).where(
                SchemaDraftRecord.tenant_id == tenant_id,
                SchemaDraftRecord.schema_id == schema_id,
            )
        )
        if exists is None:
            raise DraftNotFoundError("tenant schema draft was not found")
        raise DraftRevisionConflictError("draft revision no longer matches")

    async def add_publication(
        self,
        tenant_id: UUID,
        publication: SchemaPublication,
        *,
        previous_version: SchemaVersion | None,
    ) -> StoredSchemaPublication:
        """Flush a publication and its normalized artifact rows in one savepoint.

        @skyhook-implements REQ-003
        @skyhook-implements NFR-001
        @skyhook-implements NFR-008
        @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
        """
        _validate_publication_link(publication, previous_version)
        _require_actor(publication.provenance.actor_id)
        _require_identifier(publication.provenance.correlation_id, "correlation")
        schema = publication.schema
        compatibility = _compatibility_out(publication.compatibility)
        stored_artifacts = _stored_artifacts(schema)
        publication_values = {
            "tenant_id": tenant_id,
            "schema_id": UUID(schema.schema_id.value),
            "version": schema.version.value,
            "previous_version": None if previous_version is None else previous_version.value,
            "release_label": None if schema.release_label is None else schema.release_label.value,
            "snapshot_format": INTERCHANGE_FORMAT,
            "snapshot_format_version": INTERCHANGE_VERSION,
            "snapshot": _json_object(export_schema(schema)),
            "content_sha256": publication.content_sha256,
            "compatibility_level": (
                None if publication.compatibility is None else publication.compatibility.level.value
            ),
            "compatibility": compatibility,
            "actor_id": publication.provenance.actor_id,
            "correlation_id": publication.provenance.correlation_id,
            "acknowledgement": publication.provenance.acknowledgement,
            "published_at": publication.provenance.published_at,
        }
        artifact_values = [
            {
                "tenant_id": tenant_id,
                "reference_id": uuid4(),
                "schema_id": UUID(schema.schema_id.value),
                "schema_version": schema.version.value,
                "binding_path": item.binding_path,
                "artifact_id": UUID(item.reference.artifact_id),
                "artifact_version": item.reference.version.value,
                "kind": item.reference.kind.value,
                "content_sha256": item.reference.content_sha256,
            }
            for item in stored_artifacts
        ]
        try:
            async with self._session.begin_nested():
                await self._session.execute(
                    insert(SchemaPublicationRecord).values(**publication_values)
                )
                if artifact_values:
                    await self._session.execute(
                        insert(SchemaPublicationArtifactRecord), artifact_values
                    )
        except IntegrityError as error:
            if _constraint_name(error) == "pk_schema_publications":
                raise PublicationAlreadyExistsError(
                    "tenant schema version was already published"
                ) from error
            raise
        return StoredSchemaPublication(tenant_id, publication, previous_version, stored_artifacts)

    async def get_publication(
        self, tenant_id: UUID, schema_id: SchemaId, version: SchemaVersion
    ) -> StoredSchemaPublication | None:
        """Load and integrity-check one exact immutable publication.

        @skyhook-implements REQ-003
        @skyhook-implements NFR-001
        @skyhook-implements NFR-008
        @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
        """
        record = await self._session.scalar(
            select(SchemaPublicationRecord).where(
                SchemaPublicationRecord.tenant_id == tenant_id,
                SchemaPublicationRecord.schema_id == UUID(schema_id.value),
                SchemaPublicationRecord.version == version.value,
            )
        )
        if record is None:
            return None
        artifact_records = (
            await self._session.scalars(
                select(SchemaPublicationArtifactRecord)
                .where(
                    SchemaPublicationArtifactRecord.tenant_id == tenant_id,
                    SchemaPublicationArtifactRecord.schema_id == UUID(schema_id.value),
                    SchemaPublicationArtifactRecord.schema_version == version.value,
                )
                .order_by(
                    SchemaPublicationArtifactRecord.binding_path,
                    SchemaPublicationArtifactRecord.artifact_id,
                    SchemaPublicationArtifactRecord.artifact_version,
                    SchemaPublicationArtifactRecord.kind,
                )
            )
        ).all()
        return _stored_publication(record, artifact_records)


def _require_actor(actor_id: str) -> None:
    _require_identifier(actor_id, "actor")


def _require_identifier(value: str, subject: str) -> None:
    if not value.strip() or len(value) > 255:
        raise ValueError(f"{subject} identity must contain 1 to 255 characters")


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    value = getattr(diagnostic, "constraint_name", None)
    return value if isinstance(value, str) else None


def _json_object(payload: bytes) -> dict[str, object]:
    value: Any = json.loads(payload)
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("canonical schema payload must be a JSON object")
    return value


def _stored_draft(record: SchemaDraftRecord) -> StoredSchemaDraft:
    if record.draft_format_version != DRAFT_INTERCHANGE_VERSION:
        raise StoredSchemaIntegrityError("stored draft format version is unsupported")
    try:
        draft = import_schema_draft(json.dumps(record.definition))
    except ValueError as error:
        raise StoredSchemaIntegrityError("stored schema draft is invalid") from error
    if draft.schema_id.value != str(record.schema_id):
        raise StoredSchemaIntegrityError("stored draft identity does not match its key")
    if draft.release_label is None:
        if record.release_label is not None:
            raise StoredSchemaIntegrityError("stored draft release label does not match")
    elif draft.release_label.value != record.release_label:
        raise StoredSchemaIntegrityError("stored draft release label does not match")
    return StoredSchemaDraft(
        tenant_id=record.tenant_id,
        draft=draft,
        revision=record.revision,
        created_by=record.created_by,
        updated_by=record.updated_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _validate_publication_link(
    publication: SchemaPublication, previous_version: SchemaVersion | None
) -> None:
    if (previous_version is None) != (publication.compatibility is None):
        raise ValueError("previous version and compatibility evidence must be supplied together")
    if previous_version is not None and previous_version.value >= publication.schema.version.value:
        raise ValueError("previous publication version must precede the new version")
    if publication.content_sha256 != schema_content_sha256(publication.schema):
        raise StoredSchemaIntegrityError("publication content digest is invalid")


def _compatibility_out(report: CompatibilityReport | None) -> dict[str, object] | None:
    if report is None:
        return None
    return {
        "level": report.level.value,
        "changes": [
            {
                "code": change.code.value,
                "level": change.level.value,
                "path": None if change.path is None else str(change.path),
                "message": change.message,
            }
            for change in report.changes
        ],
    }


def _compatibility_in(raw: dict[str, object] | None) -> CompatibilityReport | None:
    if raw is None:
        return None
    level = raw.get("level")
    changes = raw.get("changes")
    if not isinstance(level, str) or not isinstance(changes, list):
        raise StoredSchemaIntegrityError("stored compatibility evidence is invalid")
    try:
        return CompatibilityReport(
            CompatibilityLevel(level),
            tuple(_change_in(item) for item in changes),
        )
    except (TypeError, ValueError) as error:
        raise StoredSchemaIntegrityError("stored compatibility evidence is invalid") from error


def _change_in(raw: object) -> SchemaChange:
    if not isinstance(raw, dict):
        raise ValueError("compatibility change must be an object")
    code, level, path, message = (
        raw.get("code"),
        raw.get("level"),
        raw.get("path"),
        raw.get("message"),
    )
    if not isinstance(code, str) or not isinstance(level, str) or not isinstance(message, str):
        raise ValueError("compatibility change fields are invalid")
    if path is not None and not isinstance(path, str):
        raise ValueError("compatibility path is invalid")
    return SchemaChange(
        SchemaChangeCode(code),
        CompatibilityLevel(level),
        None if path is None else FieldPath.parse(path),
        message,
    )


def _stored_artifacts(schema: PublishedSchemaVersion) -> tuple[StoredArtifactReference, ...]:
    items: list[StoredArtifactReference] = []
    items.extend(_binding_items("$", schema.artifacts))
    for field in schema.fields:
        items.extend(_field_binding_items(f"$.fields.{field.key.value}", field))
    for module in schema.modules:
        module_path = f"$.modules.{module.key.value}@{module.version.value}"
        items.extend(_module_binding_items(module_path, module))
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.binding_path,
                item.reference.artifact_id,
                item.reference.version.value,
                item.reference.kind.value,
            ),
        )
    )


def _module_binding_items(
    path: str, module: PublishedSchemaModule
) -> Iterable[StoredArtifactReference]:
    yield from _binding_items(path, module.artifacts)
    for field in module.fields:
        yield from _field_binding_items(f"{path}.fields.{field.key.value}", field)


def _field_binding_items(path: str, field: FieldDefinition) -> Iterable[StoredArtifactReference]:
    yield from _binding_items(f"{path}.definition", field.artifacts)
    yield from _value_binding_items(f"{path}.value", field.value)


def _value_binding_items(path: str, value: ValueDefinition) -> Iterable[StoredArtifactReference]:
    yield from _binding_items(path, value.artifacts)
    for child in value.object_fields:
        yield from _field_binding_items(f"{path}.fields.{child.key.value}", child)
    for column in value.table_columns:
        yield from _field_binding_items(f"{path}.columns.{column.key.value}", column)
    if value.array_item is not None:
        yield from _value_binding_items(f"{path}.items", value.array_item)


def _binding_items(path: str, bindings: ArtifactBindings) -> Iterable[StoredArtifactReference]:
    if len(path) > 512:
        raise ValueError("artifact binding path exceeds the persistence limit")
    for reference in bindings.references:
        yield StoredArtifactReference(path, reference)


def _stored_publication(
    record: SchemaPublicationRecord,
    artifact_records: Iterable[SchemaPublicationArtifactRecord],
) -> StoredSchemaPublication:
    try:
        schema = import_schema(json.dumps(record.snapshot)).schema
    except ValueError as error:
        raise StoredSchemaIntegrityError("stored publication snapshot is invalid") from error
    if (
        schema.schema_id.value != str(record.schema_id)
        or schema.version.value != record.version
        or record.snapshot_format != INTERCHANGE_FORMAT
        or record.snapshot_format_version != INTERCHANGE_VERSION
    ):
        raise StoredSchemaIntegrityError("stored publication identity or format does not match")
    if schema_content_sha256(schema) != record.content_sha256:
        raise StoredSchemaIntegrityError("stored publication digest does not match")
    compatibility = _compatibility_in(record.compatibility)
    if (record.previous_version is None) != (compatibility is None):
        raise StoredSchemaIntegrityError("stored previous-version evidence does not match")
    if (compatibility is None and record.compatibility_level is not None) or (
        compatibility is not None and compatibility.level.value != record.compatibility_level
    ):
        raise StoredSchemaIntegrityError("stored compatibility level does not match")
    publication = SchemaPublication(
        schema=schema,
        content_sha256=record.content_sha256,
        provenance=PublicationProvenance(
            actor_id=record.actor_id,
            correlation_id=record.correlation_id,
            published_at=record.published_at,
            acknowledgement=record.acknowledgement,
        ),
        compatibility=compatibility,
    )
    artifacts = tuple(
        StoredArtifactReference(
            binding_path=item.binding_path,
            reference=PublishedArtifactReference(
                artifact_id=str(item.artifact_id),
                version=SchemaVersion(item.artifact_version),
                kind=SchemaArtifactKind(item.kind),
                content_sha256=item.content_sha256,
            ),
        )
        for item in artifact_records
    )
    if artifacts != _stored_artifacts(schema):
        raise StoredSchemaIntegrityError("stored artifact metadata does not match the snapshot")
    return StoredSchemaPublication(
        tenant_id=record.tenant_id,
        publication=publication,
        previous_version=(
            None if record.previous_version is None else SchemaVersion(record.previous_version)
        ),
        artifacts=artifacts,
    )
