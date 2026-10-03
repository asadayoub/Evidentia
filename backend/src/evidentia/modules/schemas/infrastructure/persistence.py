"""SQLAlchemy persistence records owned exclusively by the schemas module.

The records deliberately remain separate from domain objects. Relational columns
carry identity, tenancy, concurrency, and audit invariants while JSONB retains the
canonical dynamic schema documents.

@skyhook-implements REQ-003
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMAS_DATABASE_NAMESPACE = "evidentia_schemas"

_NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class SchemaPersistenceBase(DeclarativeBase):
    """Declarative base for tables owned only by the schemas context.

    @skyhook-implements REQ-003
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


class SchemaDraftRecord(SchemaPersistenceBase):
    """Mutable tenant-owned working copy with optimistic concurrency.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """

    __tablename__ = "schema_drafts"
    __table_args__ = (
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint("draft_format_version > 0", name="draft_format_version_positive"),
        CheckConstraint("jsonb_typeof(definition) = 'object'", name="definition_is_object"),
        {"schema": SCHEMAS_DATABASE_NAMESPACE},
    )

    tenant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    schema_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    draft_format_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    release_label: Mapped[str | None] = mapped_column(String(64))
    definition: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class SchemaPublicationRecord(SchemaPersistenceBase):
    """Immutable canonical publication with digest and provenance evidence.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """

    __tablename__ = "schema_publications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "schema_id", "previous_version"],
            [
                f"{SCHEMAS_DATABASE_NAMESPACE}.schema_publications.tenant_id",
                f"{SCHEMAS_DATABASE_NAMESPACE}.schema_publications.schema_id",
                f"{SCHEMAS_DATABASE_NAMESPACE}.schema_publications.version",
            ],
            name="fk_schema_publications_previous",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "previous_version IS NULL OR previous_version < version", name="previous_version"
        ),
        CheckConstraint("snapshot_format_version > 0", name="snapshot_format_version_positive"),
        CheckConstraint("jsonb_typeof(snapshot) = 'object'", name="snapshot_is_object"),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="content_sha256_lower_hex"),
        CheckConstraint(
            "compatibility IS NULL OR jsonb_typeof(compatibility) = 'object'",
            name="compatibility_is_object",
        ),
        CheckConstraint(
            "(previous_version IS NULL AND compatibility_level IS NULL "
            "AND compatibility IS NULL) OR "
            "(previous_version IS NOT NULL AND compatibility_level IS NOT NULL "
            "AND compatibility IS NOT NULL)",
            name="compatibility_matches_previous",
        ),
        CheckConstraint(
            "compatibility_level IS NULL OR compatibility_level IN "
            "('additive_compatible', 'behavior_changing', 'breaking')",
            name="compatibility_level_known",
        ),
        Index("ix_schema_publications_tenant_published_at", "tenant_id", "published_at"),
        {"schema": SCHEMAS_DATABASE_NAMESPACE},
    )

    tenant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    schema_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    previous_version: Mapped[int | None] = mapped_column(Integer)
    release_label: Mapped[str | None] = mapped_column(String(64))
    snapshot_format: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_format_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    compatibility_level: Mapped[str | None] = mapped_column(String(32))
    compatibility: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    acknowledgement: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchemaPublicationArtifactRecord(SchemaPersistenceBase):
    """Queryable immutable artifact binding copied from a publication snapshot.

    @skyhook-implements REQ-003
    @skyhook-implements REQ-005
    @skyhook-implements REQ-006
    @skyhook-implements NFR-001
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """

    __tablename__ = "schema_publication_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "schema_id", "schema_version"],
            [
                f"{SCHEMAS_DATABASE_NAMESPACE}.schema_publications.tenant_id",
                f"{SCHEMAS_DATABASE_NAMESPACE}.schema_publications.schema_id",
                f"{SCHEMAS_DATABASE_NAMESPACE}.schema_publications.version",
            ],
            name="fk_schema_publication_artifacts_publication",
            ondelete="CASCADE",
        ),
        CheckConstraint("schema_version > 0", name="schema_version_positive"),
        CheckConstraint("artifact_version > 0", name="artifact_version_positive"),
        CheckConstraint("length(binding_path) > 0", name="binding_path_not_empty"),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="content_sha256_lower_hex"),
        CheckConstraint(
            "kind IN ('validation_rules', 'normalization_rules', 'presentation_hints', "
            "'localization', 'extraction_hints', 'evidence_expectation')",
            name="kind_known",
        ),
        UniqueConstraint(
            "tenant_id",
            "schema_id",
            "schema_version",
            "binding_path",
            "artifact_id",
            "artifact_version",
            "kind",
            name="uq_schema_publication_artifacts_binding",
        ),
        {"schema": SCHEMAS_DATABASE_NAMESPACE},
    )

    tenant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    reference_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    schema_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_path: Mapped[str] = mapped_column(String(512), nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    artifact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
