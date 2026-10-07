"""SQLAlchemy records owned exclusively by the Access and Tenancy context.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ACCESS_DATABASE_NAMESPACE = "evidentia_access"

_NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class AccessPersistenceBase(DeclarativeBase):
    """Declarative base for access-owned relational state.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


class TenantRecord(AccessPersistenceBase):
    """Durable tenant security boundary.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended')", name="status_known"),
        {"schema": ACCESS_DATABASE_NAMESPACE},
    )
    tenant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class OperatorRecord(AccessPersistenceBase):
    """Provider-independent operator account.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    __tablename__ = "operators"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="status_known"),
        {"schema": ACCESS_DATABASE_NAMESPACE},
    )
    operator_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    login_identifier: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class IdentityMappingRecord(AccessPersistenceBase):
    """Unique provider subject mapped to an operator.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    __tablename__ = "identity_mappings"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_identity_mappings_provider_subject"),
        Index("ix_identity_mappings_operator", "operator_id"),
        {"schema": ACCESS_DATABASE_NAMESPACE},
    )
    credential_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    operator_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{ACCESS_DATABASE_NAMESPACE}.operators.operator_id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class LocalPasswordCredentialRecord(AccessPersistenceBase):
    """Encoded Argon2id material for a local identity mapping.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    __tablename__ = "local_password_credentials"
    __table_args__ = (
        CheckConstraint("password_hash LIKE '$argon2id$%'", name="password_hash_argon2id"),
        {"schema": ACCESS_DATABASE_NAMESPACE},
    )
    credential_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            f"{ACCESS_DATABASE_NAMESPACE}.identity_mappings.credential_id", ondelete="CASCADE"
        ),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class MembershipRecord(AccessPersistenceBase):
    """One operator's lifecycle within one tenant.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "operator_id", name="uq_memberships_tenant_operator"),
        CheckConstraint("status IN ('active', 'suspended', 'revoked')", name="status_known"),
        Index("ix_memberships_operator", "operator_id"),
        {"schema": ACCESS_DATABASE_NAMESPACE},
    )
    membership_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{ACCESS_DATABASE_NAMESPACE}.tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    operator_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{ACCESS_DATABASE_NAMESPACE}.operators.operator_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class MembershipCapabilityRecord(AccessPersistenceBase):
    """Normalized dynamic capability grant.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    __tablename__ = "membership_capabilities"
    __table_args__ = ({"schema": ACCESS_DATABASE_NAMESPACE},)
    membership_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{ACCESS_DATABASE_NAMESPACE}.memberships.membership_id", ondelete="CASCADE"),
        primary_key=True,
    )
    capability: Mapped[str] = mapped_column(String(128), primary_key=True)


class AccessSessionRecord(AccessPersistenceBase):
    """Revocable session containing only a SHA-256 token digest.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    __tablename__ = "access_sessions"
    __table_args__ = (
        CheckConstraint("token_sha256 ~ '^[0-9a-f]{64}$'", name="token_sha256_lower_hex"),
        CheckConstraint("last_seen_at >= authenticated_at", name="last_seen_after_authentication"),
        CheckConstraint("expires_at > authenticated_at", name="expiry_after_authentication"),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= authenticated_at",
            name="revocation_after_authentication",
        ),
        CheckConstraint(
            "replaced_by_session_id IS NULL OR replaced_by_session_id <> session_id",
            name="not_self_replaced",
        ),
        Index("ix_access_sessions_operator", "operator_id"),
        Index("ix_access_sessions_expiry", "expires_at"),
        {"schema": ACCESS_DATABASE_NAMESPACE},
    )
    session_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    operator_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{ACCESS_DATABASE_NAMESPACE}.operators.operator_id", ondelete="CASCADE"),
        nullable=False,
    )
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    active_tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{ACCESS_DATABASE_NAMESPACE}.tenants.tenant_id", ondelete="SET NULL")
    )
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{ACCESS_DATABASE_NAMESPACE}.access_sessions.session_id", ondelete="SET NULL")
    )
