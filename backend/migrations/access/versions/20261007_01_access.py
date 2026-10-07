"""Create access-owned identities, memberships, credentials, and sessions.

Revision ID: 20261007_01_access
Revises: None

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261007_01_access"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("access",)
depends_on: str | Sequence[str] | None = None

_NAMESPACE = "evidentia_access"


def upgrade() -> None:
    """Create only objects owned by the access bounded context.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    op.execute(sa.schema.CreateSchema(_NAMESPACE))
    op.create_table(
        "tenants",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="ck_tenants_status_known"),
        sa.PrimaryKeyConstraint("tenant_id", name="pk_tenants"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        schema=_NAMESPACE,
    )
    op.create_table(
        "operators",
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("login_identifier", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_operators_status_known"),
        sa.PrimaryKeyConstraint("operator_id", name="pk_operators"),
        sa.UniqueConstraint("login_identifier", name="uq_operators_login_identifier"),
        schema=_NAMESPACE,
    )
    op.create_table(
        "identity_mappings",
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            [f"{_NAMESPACE}.operators.operator_id"],
            name="fk_identity_mappings_operator_id_operators",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("credential_id", name="pk_identity_mappings"),
        sa.UniqueConstraint("provider", "subject", name="uq_identity_mappings_provider_subject"),
        schema=_NAMESPACE,
    )
    op.create_index(
        "ix_identity_mappings_operator", "identity_mappings", ["operator_id"], schema=_NAMESPACE
    )
    op.create_table(
        "local_password_credentials",
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "password_hash LIKE '$argon2id$%'",
            name="ck_local_password_credentials_password_hash_argon2id",
        ),
        sa.ForeignKeyConstraint(
            ["credential_id"],
            [f"{_NAMESPACE}.identity_mappings.credential_id"],
            name="fk_local_password_credentials_credential_id_identity_mappings",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("credential_id", name="pk_local_password_credentials"),
        schema=_NAMESPACE,
    )
    op.create_table(
        "memberships",
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'revoked')", name="ck_memberships_status_known"
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            [f"{_NAMESPACE}.operators.operator_id"],
            name="fk_memberships_operator_id_operators",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{_NAMESPACE}.tenants.tenant_id"],
            name="fk_memberships_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("membership_id", name="pk_memberships"),
        sa.UniqueConstraint("tenant_id", "operator_id", name="uq_memberships_tenant_operator"),
        schema=_NAMESPACE,
    )
    op.create_index("ix_memberships_operator", "memberships", ["operator_id"], schema=_NAMESPACE)
    op.create_table(
        "membership_capabilities",
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            [f"{_NAMESPACE}.memberships.membership_id"],
            name="fk_membership_capabilities_membership_id_memberships",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("membership_id", "capability", name="pk_membership_capabilities"),
        schema=_NAMESPACE,
    )
    op.create_table(
        "access_sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("active_tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "expires_at > authenticated_at", name="ck_access_sessions_expiry_after_authentication"
        ),
        sa.CheckConstraint(
            "last_seen_at >= authenticated_at",
            name="ck_access_sessions_last_seen_after_authentication",
        ),
        sa.CheckConstraint(
            "replaced_by_session_id IS NULL OR replaced_by_session_id <> session_id",
            name="ck_access_sessions_not_self_replaced",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= authenticated_at",
            name="ck_access_sessions_revocation_after_authentication",
        ),
        sa.CheckConstraint(
            "token_sha256 ~ '^[0-9a-f]{64}$'", name="ck_access_sessions_token_sha256_lower_hex"
        ),
        sa.ForeignKeyConstraint(
            ["active_tenant_id"],
            [f"{_NAMESPACE}.tenants.tenant_id"],
            name="fk_access_sessions_active_tenant_id_tenants",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            [f"{_NAMESPACE}.operators.operator_id"],
            name="fk_access_sessions_operator_id_operators",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_session_id"],
            [f"{_NAMESPACE}.access_sessions.session_id"],
            name="fk_access_sessions_replaced_by_session_id_access_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("session_id", name="pk_access_sessions"),
        sa.UniqueConstraint("token_sha256", name="uq_access_sessions_token_sha256"),
        schema=_NAMESPACE,
    )
    op.create_index(
        "ix_access_sessions_expiry", "access_sessions", ["expires_at"], schema=_NAMESPACE
    )
    op.create_index(
        "ix_access_sessions_operator", "access_sessions", ["operator_id"], schema=_NAMESPACE
    )


def downgrade() -> None:
    """Remove only access-owned objects in dependency-safe order.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    op.drop_table("access_sessions", schema=_NAMESPACE)
    op.drop_table("membership_capabilities", schema=_NAMESPACE)
    op.drop_table("memberships", schema=_NAMESPACE)
    op.drop_table("local_password_credentials", schema=_NAMESPACE)
    op.drop_table("identity_mappings", schema=_NAMESPACE)
    op.drop_table("operators", schema=_NAMESPACE)
    op.drop_table("tenants", schema=_NAMESPACE)
    op.execute(sa.schema.DropSchema(_NAMESPACE))
