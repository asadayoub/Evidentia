"""SQLAlchemy records owned exclusively by the documents bounded context.

@skyhook-implements REQ-001
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
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
    MetaData,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DOCUMENTS_DATABASE_NAMESPACE = "evidentia_documents"
_STATUSES = "'receiving', 'preserved', 'failed', 'rejected', 'cancelled'"
_FAILURES = "'storage_unavailable', 'integrity_mismatch', 'persistence_conflict', 'cancelled'"
_NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class DocumentPersistenceBase(DeclarativeBase):
    """Declarative base for tables owned only by document custody.

    @skyhook-implements REQ-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


class DocumentRecord(DocumentPersistenceBase):
    """Mutable custody state whose preserved artifact facts are immutable by policy.

    @skyhook-implements REQ-001
    @skyhook-implements NFR-002
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUSES})", name="status_known"),
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint("byte_size > 0", name="byte_size_positive"),
        CheckConstraint(
            "content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'",
            name="content_sha256_lower_hex",
        ),
        CheckConstraint(
            f"failure_code IS NULL OR failure_code IN ({_FAILURES})", name="failure_code_known"
        ),
        CheckConstraint(
            "(status = 'receiving' AND content_sha256 IS NULL AND storage_key IS NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'preserved' AND content_sha256 IS NOT NULL AND storage_key IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status IN ('failed', 'rejected', 'cancelled') AND content_sha256 IS NULL "
            "AND storage_key IS NULL AND failure_code IS NOT NULL)",
            name="state_fields",
        ),
        Index("ix_documents_tenant_created_at", "tenant_id", "created_at"),
        Index(
            "ix_documents_tenant_digest",
            "tenant_id",
            "content_sha256",
            postgresql_where=text("content_sha256 IS NOT NULL"),
        ),
        {"schema": DOCUMENTS_DATABASE_NAMESPACE},
    )

    tenant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    storage_key: Mapped[str | None] = mapped_column(String(512))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentUploadAttemptRecord(DocumentPersistenceBase):
    """Tenant-scoped durable retry and recovery state.

    @skyhook-implements NFR-003
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    __tablename__ = "document_upload_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            [
                f"{DOCUMENTS_DATABASE_NAMESPACE}.documents.tenant_id",
                f"{DOCUMENTS_DATABASE_NAMESPACE}.documents.document_id",
            ],
            name="fk_upload_attempts_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"status IN ({_STATUSES})", name="status_known"),
        CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="request_sha256_lower_hex"),
        CheckConstraint(
            f"failure_code IS NULL OR failure_code IN ({_FAILURES})", name="failure_code_known"
        ),
        CheckConstraint(
            "(status = 'receiving' AND completed_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'preserved' AND completed_at IS NOT NULL AND failure_code IS NULL) OR "
            "(status IN ('failed', 'rejected', 'cancelled') AND completed_at IS NOT NULL "
            "AND failure_code IS NOT NULL)",
            name="state_fields",
        ),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_document_upload_attempts_retry"),
        Index("ix_document_upload_attempts_tenant_document", "tenant_id", "document_id"),
        {"schema": DOCUMENTS_DATABASE_NAMESPACE},
    )

    tenant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    attempt_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(64))


class DocumentCustodyEventRecord(DocumentPersistenceBase):
    """Append-only audit fact for one custody revision.

    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    __tablename__ = "document_custody_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            [
                f"{DOCUMENTS_DATABASE_NAMESPACE}.documents.tenant_id",
                f"{DOCUMENTS_DATABASE_NAMESPACE}.documents.document_id",
            ],
            name="fk_custody_events_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_STATUSES})", name="from_status_known"
        ),
        CheckConstraint(f"to_status IN ({_STATUSES})", name="to_status_known"),
        CheckConstraint(
            f"reason_code IS NULL OR reason_code IN ({_FAILURES})", name="reason_code_known"
        ),
        CheckConstraint("document_revision > 0", name="revision_positive"),
        UniqueConstraint(
            "tenant_id",
            "document_id",
            "document_revision",
            name="uq_custody_events_document_revision",
        ),
        Index(
            "ix_document_custody_events_tenant_document_time",
            "tenant_id",
            "document_id",
            "occurred_at",
        ),
        {"schema": DOCUMENTS_DATABASE_NAMESPACE},
    )

    tenant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    document_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
