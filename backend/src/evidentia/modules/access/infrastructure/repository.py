"""Async PostgreSQL repositories for access-owned aggregates.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from evidentia.modules.access.application.ports import Argon2idPasswordHash
from evidentia.modules.access.domain.identity import (
    Capability,
    CredentialId,
    IdentityProviderKey,
    LoginIdentifier,
    MembershipId,
    OperatorId,
    ProviderSubject,
    SessionId,
    SessionTokenDigest,
    TenantId,
    TenantSlug,
)
from evidentia.modules.access.domain.models import (
    AccessSession,
    CredentialIdentity,
    Membership,
    MembershipStatus,
    Operator,
    OperatorStatus,
    Tenant,
    TenantStatus,
)
from evidentia.modules.access.infrastructure.persistence import (
    AccessSessionRecord,
    IdentityMappingRecord,
    LocalPasswordCredentialRecord,
    MembershipCapabilityRecord,
    MembershipRecord,
    OperatorRecord,
    TenantRecord,
)


class PostgresOperatorRepository:
    """Transaction-neutral operator adapter.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, operator: Operator) -> None:
        """Stage and flush an operator in the caller transaction."""
        self._session.add(
            OperatorRecord(
                operator_id=UUID(operator.operator_id.value),
                login_identifier=operator.login_identifier.value,
                display_name=operator.display_name,
                status=operator.status.value,
            )
        )
        await self._session.flush()

    async def get(self, operator_id: OperatorId) -> Operator | None:
        """Load an operator by opaque identity."""
        record = await self._session.get(OperatorRecord, UUID(operator_id.value))
        return None if record is None else _operator(record)

    async def get_by_login_identifier(self, login_identifier: LoginIdentifier) -> Operator | None:
        """Load an operator by normalized login identifier."""
        record = await self._session.scalar(
            select(OperatorRecord).where(OperatorRecord.login_identifier == login_identifier.value)
        )
        return None if record is None else _operator(record)


class PostgresTenantRepository:
    """Transaction-neutral tenant adapter.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tenant: Tenant) -> None:
        """Stage and flush a tenant in the caller transaction."""
        self._session.add(
            TenantRecord(
                tenant_id=UUID(tenant.tenant_id.value),
                slug=tenant.slug.value,
                display_name=tenant.display_name,
                status=tenant.status.value,
            )
        )
        await self._session.flush()

    async def get(self, tenant_id: TenantId) -> Tenant | None:
        """Load a tenant by opaque identity."""
        record = await self._session.get(TenantRecord, UUID(tenant_id.value))
        return None if record is None else _tenant(record)

    async def get_by_slug(self, slug: TenantSlug) -> Tenant | None:
        """Load a tenant by canonical slug."""
        record = await self._session.scalar(
            select(TenantRecord).where(TenantRecord.slug == slug.value)
        )
        return None if record is None else _tenant(record)


class PostgresMembershipRepository:
    """Tenant-isolated membership and dynamic capability adapter.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, membership: Membership) -> None:
        """Stage one membership and its normalized capability rows."""
        membership_uuid = UUID(membership.membership_id.value)
        self._session.add(
            MembershipRecord(
                membership_id=membership_uuid,
                tenant_id=UUID(membership.tenant_id.value),
                operator_id=UUID(membership.operator_id.value),
                status=membership.status.value,
            )
        )
        await self._session.flush()
        self._session.add_all(
            MembershipCapabilityRecord(
                membership_id=membership_uuid,
                capability=capability.value,
            )
            for capability in sorted(membership.capabilities)
        )
        await self._session.flush()

    async def get(self, membership_id: MembershipId) -> Membership | None:
        """Load a membership by opaque identity."""
        record = await self._session.get(MembershipRecord, UUID(membership_id.value))
        return await self._membership(record)

    async def get_for_operator_and_tenant(
        self,
        operator_id: OperatorId,
        tenant_id: TenantId,
    ) -> Membership | None:
        """Load only the relationship matching both security principals."""
        record = await self._session.scalar(
            select(MembershipRecord).where(
                MembershipRecord.operator_id == UUID(operator_id.value),
                MembershipRecord.tenant_id == UUID(tenant_id.value),
            )
        )
        return await self._membership(record)

    async def list_for_operator(self, operator_id: OperatorId) -> tuple[Membership, ...]:
        """List deterministic memberships belonging only to one operator."""
        records = (
            await self._session.scalars(
                select(MembershipRecord)
                .where(MembershipRecord.operator_id == UUID(operator_id.value))
                .order_by(MembershipRecord.tenant_id)
            )
        ).all()
        memberships = [await self._membership(record) for record in records]
        return tuple(item for item in memberships if item is not None)

    async def replace(self, membership: Membership) -> None:
        """Replace lifecycle state and capability grants atomically when committed."""
        membership_uuid = UUID(membership.membership_id.value)
        await self._session.execute(
            update(MembershipRecord)
            .where(MembershipRecord.membership_id == membership_uuid)
            .values(status=membership.status.value)
        )
        await self._session.execute(
            delete(MembershipCapabilityRecord).where(
                MembershipCapabilityRecord.membership_id == membership_uuid
            )
        )
        self._session.add_all(
            MembershipCapabilityRecord(
                membership_id=membership_uuid,
                capability=capability.value,
            )
            for capability in sorted(membership.capabilities)
        )
        await self._session.flush()

    async def _membership(self, record: MembershipRecord | None) -> Membership | None:
        if record is None:
            return None
        capabilities = (
            await self._session.scalars(
                select(MembershipCapabilityRecord.capability)
                .where(MembershipCapabilityRecord.membership_id == record.membership_id)
                .order_by(MembershipCapabilityRecord.capability)
            )
        ).all()
        return Membership(
            membership_id=MembershipId(str(record.membership_id)),
            tenant_id=TenantId(str(record.tenant_id)),
            operator_id=OperatorId(str(record.operator_id)),
            capabilities=frozenset(Capability(item) for item in capabilities),
            status=MembershipStatus(record.status),
        )


class PostgresCredentialRepository:
    """Provider mapping adapter that never returns an unwrapped encoded hash.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        credential: CredentialIdentity,
        password_hash: Argon2idPasswordHash | None = None,
    ) -> None:
        """Stage a mapping and optional local verifier in one transaction."""
        if password_hash is not None and credential.provider.value != "local":
            raise ValueError("password hashes may only be attached to the local provider")
        credential_uuid = UUID(credential.credential_id.value)
        self._session.add(
            IdentityMappingRecord(
                credential_id=credential_uuid,
                operator_id=UUID(credential.operator_id.value),
                provider=credential.provider.value,
                subject=credential.subject.value,
            )
        )
        await self._session.flush()
        if password_hash is not None:
            self._session.add(
                LocalPasswordCredentialRecord(
                    credential_id=credential_uuid,
                    password_hash=password_hash.reveal(),
                )
            )
        await self._session.flush()

    async def get_by_provider_subject(
        self,
        provider: IdentityProviderKey,
        subject: ProviderSubject,
    ) -> CredentialIdentity | None:
        """Load the globally unique mapping for a provider subject."""
        record = await self._session.scalar(
            select(IdentityMappingRecord).where(
                IdentityMappingRecord.provider == provider.value,
                IdentityMappingRecord.subject == subject.value,
            )
        )
        return None if record is None else _credential(record)

    async def get_local_password_hash(
        self, credential_id: CredentialId
    ) -> Argon2idPasswordHash | None:
        """Load local verifier material through its redacting value type."""
        value = await self._session.scalar(
            select(LocalPasswordCredentialRecord.password_hash).where(
                LocalPasswordCredentialRecord.credential_id == UUID(credential_id.value)
            )
        )
        return None if value is None else Argon2idPasswordHash(value)

    async def replace_local_password_hash(
        self,
        credential_id: CredentialId,
        password_hash: Argon2idPasswordHash,
    ) -> None:
        """Rotate an existing local verifier without changing identity."""
        await self._session.execute(
            update(LocalPasswordCredentialRecord)
            .where(LocalPasswordCredentialRecord.credential_id == UUID(credential_id.value))
            .values(password_hash=password_hash.reveal())
        )
        await self._session.flush()


class PostgresSessionRepository:
    """Hashed-token session adapter with expiry and revocation metadata.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: AccessSession, token_digest: SessionTokenDigest) -> None:
        """Stage a session while persisting only its SHA-256 digest."""
        self._session.add(_session_record(session, token_digest.value))
        await self._session.flush()

    async def get_by_digest(self, token_digest: SessionTokenDigest) -> AccessSession | None:
        """Load a session by non-reversible token digest."""
        record = await self._session.scalar(
            select(AccessSessionRecord).where(
                AccessSessionRecord.token_sha256 == token_digest.value
            )
        )
        return None if record is None else _session(record)

    async def replace(self, session: AccessSession) -> None:
        """Persist mutable session metadata without changing its token digest."""
        await self._session.execute(
            update(AccessSessionRecord)
            .where(
                AccessSessionRecord.session_id == UUID(session.session_id.value),
                AccessSessionRecord.revoked_at.is_(None),
            )
            .values(
                active_tenant_id=(
                    None
                    if session.active_tenant_id is None
                    else UUID(session.active_tenant_id.value)
                ),
                last_seen_at=session.last_seen_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
                replaced_by_session_id=(
                    None
                    if session.replaced_by_session_id is None
                    else UUID(session.replaced_by_session_id.value)
                ),
            )
        )
        await self._session.flush()

    async def get(self, session_id: SessionId) -> AccessSession | None:
        """Load a session by opaque identity."""
        record = await self._session.get(AccessSessionRecord, UUID(session_id.value))
        return None if record is None else _session(record)

    async def revoke_if_active(
        self,
        session_id: SessionId,
        *,
        revoked_at: datetime,
        replaced_by_session_id: SessionId | None = None,
    ) -> bool:
        """Atomically revoke exactly one currently unrevoked session."""
        result = await self._session.execute(
            update(AccessSessionRecord)
            .where(
                AccessSessionRecord.session_id == UUID(session_id.value),
                AccessSessionRecord.revoked_at.is_(None),
            )
            .values(
                revoked_at=revoked_at,
                replaced_by_session_id=(
                    None if replaced_by_session_id is None else UUID(replaced_by_session_id.value)
                ),
            )
            .returning(AccessSessionRecord.session_id)
        )
        return result.scalar_one_or_none() is not None

    async def delete(self, session_id: SessionId) -> None:
        """Delete a session staged by a rotation that lost its atomic claim."""
        await self._session.execute(
            delete(AccessSessionRecord).where(
                AccessSessionRecord.session_id == UUID(session_id.value)
            )
        )
        await self._session.flush()

    async def touch_if_active(
        self,
        session_id: SessionId,
        *,
        last_seen_at: datetime,
        expires_at: datetime,
    ) -> bool:
        """Refresh activity only while concurrent revocation has not won."""
        result = await self._session.execute(
            update(AccessSessionRecord)
            .where(
                AccessSessionRecord.session_id == UUID(session_id.value),
                AccessSessionRecord.revoked_at.is_(None),
            )
            .values(last_seen_at=last_seen_at, expires_at=expires_at)
            .returning(AccessSessionRecord.session_id)
        )
        return result.scalar_one_or_none() is not None


def _operator(record: OperatorRecord) -> Operator:
    return Operator(
        OperatorId(str(record.operator_id)),
        LoginIdentifier(record.login_identifier),
        record.display_name,
        OperatorStatus(record.status),
    )


def _tenant(record: TenantRecord) -> Tenant:
    return Tenant(
        TenantId(str(record.tenant_id)),
        TenantSlug(record.slug),
        record.display_name,
        TenantStatus(record.status),
    )


def _credential(record: IdentityMappingRecord) -> CredentialIdentity:
    return CredentialIdentity(
        CredentialId(str(record.credential_id)),
        OperatorId(str(record.operator_id)),
        IdentityProviderKey(record.provider),
        ProviderSubject(record.subject),
    )


def _session_record(session: AccessSession, digest: str) -> AccessSessionRecord:
    return AccessSessionRecord(
        session_id=UUID(session.session_id.value),
        operator_id=UUID(session.operator_id.value),
        token_sha256=digest,
        active_tenant_id=(
            None if session.active_tenant_id is None else UUID(session.active_tenant_id.value)
        ),
        authenticated_at=session.authenticated_at,
        last_seen_at=session.last_seen_at,
        expires_at=session.expires_at,
        revoked_at=session.revoked_at,
        replaced_by_session_id=(
            None
            if session.replaced_by_session_id is None
            else UUID(session.replaced_by_session_id.value)
        ),
    )


def _session(record: AccessSessionRecord) -> AccessSession:
    return AccessSession(
        session_id=SessionId(str(record.session_id)),
        operator_id=OperatorId(str(record.operator_id)),
        authenticated_at=_utc(record.authenticated_at),
        last_seen_at=_utc(record.last_seen_at),
        expires_at=_utc(record.expires_at),
        revoked_at=None if record.revoked_at is None else _utc(record.revoked_at),
        active_tenant_id=(
            None if record.active_tenant_id is None else TenantId(str(record.active_tenant_id))
        ),
        replaced_by_session_id=(
            None
            if record.replaced_by_session_id is None
            else SessionId(str(record.replaced_by_session_id))
        ),
    )


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)
