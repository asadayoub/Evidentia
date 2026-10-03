"""Publication invariants for immutable schema snapshots."""

from datetime import UTC, datetime

import pytest

from evidentia.modules.schemas.public import (
    ArtifactBindings,
    FieldDefinition,
    FieldKey,
    PublishedArtifactReference,
    PublishedSchemaVersion,
    SchemaArtifactKind,
    SchemaDraft,
    SchemaId,
    SchemaVersion,
    StringType,
    ValueDefinition,
    publish_schema,
)

SCHEMA_ID = SchemaId("123e4567-e89b-12d3-a456-426614174000")
ARTIFACT_ID = "550e8400-e29b-41d4-a716-446655440000"
DIGEST = "a" * 64


def _field(key: str) -> FieldDefinition:
    return FieldDefinition(FieldKey(key), ValueDefinition.scalar(StringType()))


def _draft(version: int, *fields: FieldDefinition) -> SchemaDraft:
    return SchemaDraft(SCHEMA_ID, SchemaVersion(version), fields=tuple(fields))


def test_publication_freezes_snapshot_digest_and_provenance() -> None:
    instant = datetime(2026, 10, 3, tzinfo=UTC)
    first = publish_schema(
        _draft(1, _field("invoice_number")),
        actor_id="user-1",
        correlation_id="request-1",
        available_artifacts={},
        published_at=instant,
    )
    repeated = publish_schema(
        _draft(1, _field("invoice_number")),
        actor_id="user-1",
        correlation_id="request-2",
        available_artifacts={},
        published_at=instant,
    )

    assert first.schema.version == SchemaVersion(1)
    assert first.content_sha256 == repeated.content_sha256
    assert first.provenance.published_at == instant
    assert len(first.content_sha256) == 64


def test_publication_verifies_every_artifact_digest() -> None:
    reference = PublishedArtifactReference(
        ARTIFACT_ID, SchemaVersion(2), SchemaArtifactKind.VALIDATION_RULES, DIGEST
    )
    draft = SchemaDraft(
        SCHEMA_ID,
        SchemaVersion(1),
        fields=(_field("invoice_number"),),
        artifacts=ArtifactBindings((reference,)),
    )
    key = (ARTIFACT_ID, 2, SchemaArtifactKind.VALIDATION_RULES.value)

    with pytest.raises(ValueError, match="missing or has the wrong digest"):
        publish_schema(draft, actor_id="user-1", correlation_id="r1", available_artifacts={})

    publication = publish_schema(
        draft,
        actor_id="user-1",
        correlation_id="r1",
        available_artifacts={key: DIGEST},
    )
    assert publication.schema.artifacts.references == (reference,)


def test_publication_rejects_duplicate_version_and_requires_acknowledgement() -> None:
    previous = PublishedSchemaVersion(SCHEMA_ID, SchemaVersion(1), fields=(_field("legacy"),))
    candidate = _draft(2, _field("replacement"))

    with pytest.raises(ValueError, match="requires acknowledgement"):
        publish_schema(
            candidate,
            actor_id="user-1",
            correlation_id="r1",
            available_artifacts={},
            previous=previous,
        )

    publication = publish_schema(
        candidate,
        actor_id="user-1",
        correlation_id="r1",
        available_artifacts={},
        previous=previous,
        acknowledgement="Reviewed breaking field replacement",
    )
    assert publication.compatibility is not None
    assert publication.compatibility.requires_acknowledgement is True

    with pytest.raises(ValueError, match="already been published"):
        publish_schema(
            candidate,
            actor_id="user-1",
            correlation_id="r2",
            available_artifacts={},
            existing_versions=(publication.schema,),
        )
