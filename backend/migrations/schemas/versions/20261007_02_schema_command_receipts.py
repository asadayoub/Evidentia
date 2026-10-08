"""Create durable schema API command receipts.

Revision ID: 20261007_02_schema_receipts
Revises: 20261003_01_schemas

@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story X51S43NTMRW5ASYSKJBF7FW845
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261007_02_schema_receipts"
down_revision: str | None = "20261003_01_schemas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMESPACE = "evidentia_schemas"


def upgrade() -> None:
    """Add an empty receipts table without changing existing records."""
    op.create_table(
        "schema_command_receipts",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(idempotency_key) > 0",
            name="ck_schema_command_receipts_idempotency_key_not_empty",
        ),
        sa.CheckConstraint(
            "length(operation) > 0", name="ck_schema_command_receipts_operation_not_empty"
        ),
        sa.CheckConstraint(
            "request_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_schema_command_receipts_request_sha256_lower_hex",
        ),
        sa.CheckConstraint(
            "(response_status IS NULL AND response_body IS NULL) OR "
            "(response_status BETWEEN 200 AND 299 AND jsonb_typeof(response_body) = 'object')",
            name="ck_schema_command_receipts_response_completion",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "operation",
            "idempotency_key",
            name="pk_schema_command_receipts",
        ),
        schema=_NAMESPACE,
    )


def downgrade() -> None:
    """Remove only schema API command receipts."""
    op.drop_table("schema_command_receipts", schema=_NAMESPACE)
