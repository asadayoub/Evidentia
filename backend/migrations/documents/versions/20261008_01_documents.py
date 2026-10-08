"""Create document custody, upload-attempt, and event persistence.

Revision ID: 20261008_01_documents
Revises: None

@skyhook-implements REQ-001
@skyhook-implements REQ-015
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements NFR-003
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_01_documents"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("documents",)
depends_on: str | Sequence[str] | None = None

_NAMESPACE = "evidentia_documents"
_STATUSES = "'receiving', 'preserved', 'failed', 'rejected', 'cancelled'"
_FAILURES = "'storage_unavailable', 'integrity_mismatch', 'persistence_conflict', 'cancelled'"


def upgrade() -> None:
    """Create additive, tenant-scoped document custody tables.

    @skyhook-implements REQ-001
    @skyhook-implements NFR-001
    @skyhook-implements NFR-002
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """
    op.execute(sa.schema.CreateSchema(_NAMESPACE))
    op.create_table(
        "documents",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_documents_status_known"),
        sa.CheckConstraint("revision > 0", name="ck_documents_revision_positive"),
        sa.CheckConstraint("byte_size > 0", name="ck_documents_byte_size_positive"),
        sa.CheckConstraint(
            "content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_documents_content_sha256_lower_hex",
        ),
        sa.CheckConstraint(
            f"failure_code IS NULL OR failure_code IN ({_FAILURES})",
            name="ck_documents_failure_code_known",
        ),
        sa.CheckConstraint(
            "(status = 'receiving' AND content_sha256 IS NULL AND storage_key IS NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'preserved' AND content_sha256 IS NOT NULL AND storage_key IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status IN ('failed', 'rejected', 'cancelled') AND content_sha256 IS NULL "
            "AND storage_key IS NULL AND failure_code IS NOT NULL)",
            name="ck_documents_state_fields",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "document_id", name="pk_documents"),
        schema=_NAMESPACE,
    )
    op.create_index(
        "ix_documents_tenant_created_at",
        "documents",
        ["tenant_id", "created_at"],
        schema=_NAMESPACE,
    )
    op.create_index(
        "ix_documents_tenant_digest",
        "documents",
        ["tenant_id", "content_sha256"],
        schema=_NAMESPACE,
        postgresql_where=sa.text("content_sha256 IS NOT NULL"),
    )
    op.create_table(
        "document_upload_attempts",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_upload_attempts_status_known"),
        sa.CheckConstraint(
            "request_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_upload_attempts_request_sha256_lower_hex",
        ),
        sa.CheckConstraint(
            f"failure_code IS NULL OR failure_code IN ({_FAILURES})",
            name="ck_upload_attempts_failure_code_known",
        ),
        sa.CheckConstraint(
            "(status = 'receiving' AND completed_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'preserved' AND completed_at IS NOT NULL AND failure_code IS NULL) OR "
            "(status IN ('failed', 'rejected', 'cancelled') AND completed_at IS NOT NULL "
            "AND failure_code IS NOT NULL)",
            name="ck_upload_attempts_state_fields",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            [f"{_NAMESPACE}.documents.tenant_id", f"{_NAMESPACE}.documents.document_id"],
            name="fk_upload_attempts_document",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "attempt_id", name="pk_document_upload_attempts"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_document_upload_attempts_retry"
        ),
        schema=_NAMESPACE,
    )
    op.create_index(
        "ix_document_upload_attempts_tenant_document",
        "document_upload_attempts",
        ["tenant_id", "document_id"],
        schema=_NAMESPACE,
    )
    op.create_table(
        "document_custody_events",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_revision", sa.BigInteger(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_STATUSES})",
            name="ck_custody_events_from_status_known",
        ),
        sa.CheckConstraint(f"to_status IN ({_STATUSES})", name="ck_custody_events_to_status_known"),
        sa.CheckConstraint(
            f"reason_code IS NULL OR reason_code IN ({_FAILURES})",
            name="ck_custody_events_reason_code_known",
        ),
        sa.CheckConstraint("document_revision > 0", name="ck_custody_events_revision_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            [f"{_NAMESPACE}.documents.tenant_id", f"{_NAMESPACE}.documents.document_id"],
            name="fk_custody_events_document",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "event_id", name="pk_document_custody_events"),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "document_revision",
            name="uq_custody_events_document_revision",
        ),
        schema=_NAMESPACE,
    )
    op.create_index(
        "ix_document_custody_events_tenant_document_time",
        "document_custody_events",
        ["tenant_id", "document_id", "occurred_at"],
        schema=_NAMESPACE,
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {_NAMESPACE}.reject_custody_event_change()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'document custody events are append-only'
                    USING ERRCODE = '55000';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER reject_document_custody_event_change
            BEFORE UPDATE OR DELETE ON {_NAMESPACE}.document_custody_events
            FOR EACH ROW EXECUTE FUNCTION {_NAMESPACE}.reject_custody_event_change()
            """
        )
    )


def downgrade() -> None:
    """Remove only the additive objects owned by the documents context.

    @skyhook-implements REQ-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """
    op.drop_index(
        "ix_document_custody_events_tenant_document_time",
        table_name="document_custody_events",
        schema=_NAMESPACE,
    )
    op.drop_table("document_custody_events", schema=_NAMESPACE)
    op.execute(sa.text(f"DROP FUNCTION {_NAMESPACE}.reject_custody_event_change()"))
    op.drop_index(
        "ix_document_upload_attempts_tenant_document",
        table_name="document_upload_attempts",
        schema=_NAMESPACE,
    )
    op.drop_table("document_upload_attempts", schema=_NAMESPACE)
    op.drop_index("ix_documents_tenant_digest", table_name="documents", schema=_NAMESPACE)
    op.drop_index("ix_documents_tenant_created_at", table_name="documents", schema=_NAMESPACE)
    op.drop_table("documents", schema=_NAMESPACE)
    op.execute(sa.schema.DropSchema(_NAMESPACE))
