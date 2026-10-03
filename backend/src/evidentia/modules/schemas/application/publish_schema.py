"""Persistence-independent schema publication command."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from evidentia.modules.schemas.domain.artifact_links import (
    ArtifactBindings,
    PublishedArtifactReference,
)
from evidentia.modules.schemas.domain.compatibility import (
    CompatibilityReport,
    compare_schema_versions,
)
from evidentia.modules.schemas.domain.definitions import FieldDefinition
from evidentia.modules.schemas.domain.identity import ReleaseLabel, SchemaId, SchemaVersion
from evidentia.modules.schemas.domain.modules import PublishedSchemaModule, PublishedSchemaVersion

ArtifactKey = tuple[str, int, str]


@dataclass(frozen=True, slots=True)
class SchemaDraft:
    """Validated input used to create one new immutable publication.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    schema_id: SchemaId
    version: SchemaVersion
    fields: tuple[FieldDefinition, ...] = ()
    modules: tuple[PublishedSchemaModule, ...] = ()
    release_label: ReleaseLabel | None = None
    artifacts: ArtifactBindings = field(default_factory=ArtifactBindings)


@dataclass(frozen=True, slots=True)
class PublicationProvenance:
    """Actor and request evidence retained with a publication.

    @skyhook-implements NFR-001
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    actor_id: str
    correlation_id: str
    published_at: datetime
    acknowledgement: str | None = None

    def __post_init__(self) -> None:
        if not self.actor_id.strip() or not self.correlation_id.strip():
            raise ValueError("publication actor and correlation identifiers are required")
        if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
            raise ValueError("publication timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SchemaPublication:
    """Immutable published snapshot, digest, compatibility, and provenance.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    schema: PublishedSchemaVersion
    content_sha256: str
    provenance: PublicationProvenance
    compatibility: CompatibilityReport | None


def publish_schema(
    draft: SchemaDraft,
    *,
    actor_id: str,
    correlation_id: str,
    available_artifacts: Mapping[ArtifactKey, str],
    existing_versions: tuple[PublishedSchemaVersion, ...] = (),
    previous: PublishedSchemaVersion | None = None,
    acknowledgement: str | None = None,
    published_at: datetime | None = None,
) -> SchemaPublication:
    """Validate and freeze a draft, rejecting unsafe or duplicate publication.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """
    if any(
        item.schema_id == draft.schema_id and item.version == draft.version
        for item in existing_versions
    ):
        raise ValueError("schema version has already been published")
    schema = PublishedSchemaVersion(
        schema_id=draft.schema_id,
        version=draft.version,
        fields=draft.fields,
        modules=draft.modules,
        release_label=draft.release_label,
        artifacts=draft.artifacts,
    )
    for reference in _artifact_references(schema):
        key = (reference.artifact_id, reference.version.value, reference.kind.value)
        if available_artifacts.get(key) != reference.content_sha256:
            raise ValueError(
                f"published artifact is missing or has the wrong digest: {reference.artifact_id}"
            )
    report = compare_schema_versions(previous, schema) if previous is not None else None
    if report is not None and report.requires_acknowledgement and not acknowledgement:
        raise ValueError("behavior-changing or breaking publication requires acknowledgement")
    provenance = PublicationProvenance(
        actor_id=actor_id,
        correlation_id=correlation_id,
        published_at=published_at or datetime.now(UTC),
        acknowledgement=acknowledgement,
    )
    return SchemaPublication(schema, schema_content_sha256(schema), provenance, report)


def schema_content_sha256(schema: PublishedSchemaVersion) -> str:
    """Return the canonical content digest used by publication persistence.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    payload = json.dumps(
        _canonical(schema), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _artifact_references(schema: PublishedSchemaVersion) -> tuple[PublishedArtifactReference, ...]:
    references = list(schema.artifacts.references)
    for definition in schema.fields:
        references.extend(_field_artifacts(definition))
    for module in schema.modules:
        references.extend(module.artifacts.references)
        for definition in module.fields:
            references.extend(_field_artifacts(definition))
    return tuple(references)


def _field_artifacts(field: FieldDefinition) -> tuple[PublishedArtifactReference, ...]:
    references = [*field.artifacts.references, *field.value.artifacts.references]
    children = field.value.object_fields or field.value.table_columns
    if field.value.array_item is not None:
        references.extend(field.value.array_item.artifacts.references)
        children = field.value.array_item.object_fields
    for child in children:
        references.extend(_field_artifacts(child))
    return tuple(references)


def _canonical(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value
