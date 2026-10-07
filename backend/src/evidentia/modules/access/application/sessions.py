"""Opaque revocable session lifecycle independent of HTTP transport.

@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from evidentia.modules.access.application.ports import (
    MembershipRepository,
    OpaqueSessionToken,
    OperatorRepository,
    SessionRepository,
    SessionTokenProvider,
    TenantRepository,
)
from evidentia.modules.access.domain.identity import OperatorId, SessionId, TenantId
from evidentia.modules.access.domain.models import (
    AccessSession,
    Membership,
    MembershipStatus,
    Operator,
    OperatorStatus,
    Tenant,
    TenantStatus,
)


class SessionDenialReason(StrEnum):
    """Internal reason codes for safe interface-layer error mapping.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    INVALID = "invalid"
    INACTIVE = "inactive"
    OPERATOR_INACTIVE = "operator_inactive"
    TENANT_INACTIVE = "tenant_inactive"
    MEMBERSHIP_INACTIVE = "membership_inactive"
    TOKEN_REUSE = "token_reuse"
    ROTATION_CONFLICT = "rotation_conflict"


class SessionDeniedError(PermissionError):
    """Typed session denial whose public message remains generic.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(self, reason: SessionDenialReason) -> None:
        super().__init__("session is not valid")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """New session metadata paired with its one-time raw bearer token.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    session: AccessSession
    token: OpaqueSessionToken


@dataclass(frozen=True, slots=True)
class ValidatedSession:
    """Verified session principal and optional active tenant relationship.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    session: AccessSession
    operator: Operator
    tenant: Tenant | None
    membership: Membership | None


class ManageSessions:
    """Issue, validate, rotate, and revoke opaque sessions transactionally.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(
        self,
        sessions: SessionRepository,
        operators: OperatorRepository,
        tenants: TenantRepository,
        memberships: MembershipRepository,
        tokens: SessionTokenProvider,
        *,
        idle_timeout_seconds: int,
        absolute_timeout_seconds: int,
    ) -> None:
        if not 1 <= idle_timeout_seconds <= absolute_timeout_seconds:
            raise ValueError("session idle timeout must be positive and within absolute timeout")
        self._sessions = sessions
        self._operators = operators
        self._tenants = tenants
        self._memberships = memberships
        self._tokens = tokens
        self._idle_timeout = timedelta(seconds=idle_timeout_seconds)
        self._absolute_timeout = timedelta(seconds=absolute_timeout_seconds)

    async def issue(
        self,
        operator_id: OperatorId,
        *,
        now: datetime,
        active_tenant_id: TenantId | None = None,
    ) -> IssuedSession:
        """Issue a persisted session after revalidating operator and tenant state."""
        _require_utc(now)
        operator = await self._active_operator(operator_id)
        if active_tenant_id is not None:
            await self._active_tenant_membership(operator.operator_id, active_tenant_id)
        token = self._tokens.issue()
        session = AccessSession(
            SessionId.new(),
            operator.operator_id,
            now,
            now,
            min(now + self._idle_timeout, now + self._absolute_timeout),
            active_tenant_id=active_tenant_id,
        )
        await self._sessions.add(session, self._tokens.digest(token))
        return IssuedSession(session, token)

    async def validate(
        self,
        token: OpaqueSessionToken,
        *,
        now: datetime,
    ) -> ValidatedSession:
        """Validate, detect reuse, and extend idle expiry up to the absolute limit."""
        _require_utc(now)
        session = await self._sessions.get_by_digest(self._tokens.digest(token))
        if session is None:
            raise SessionDeniedError(SessionDenialReason.INVALID)
        if session.revoked_at is not None:
            if session.replaced_by_session_id is not None:
                await self._revoke_successors(session.replaced_by_session_id, now=now)
                raise SessionDeniedError(SessionDenialReason.TOKEN_REUSE)
            raise SessionDeniedError(SessionDenialReason.INACTIVE)
        if not session.is_active_at(now):
            raise SessionDeniedError(SessionDenialReason.INACTIVE)
        operator = await self._active_operator(
            session.operator_id, session_id=session.session_id, now=now
        )
        tenant: Tenant | None = None
        membership: Membership | None = None
        if session.active_tenant_id is not None:
            tenant, membership = await self._active_tenant_membership(
                operator.operator_id,
                session.active_tenant_id,
                session_id=session.session_id,
                now=now,
            )
        refreshed = replace(
            session,
            last_seen_at=now,
            expires_at=min(
                now + self._idle_timeout,
                session.authenticated_at + self._absolute_timeout,
            ),
        )
        touched = await self._sessions.touch_if_active(
            session.session_id,
            last_seen_at=refreshed.last_seen_at,
            expires_at=refreshed.expires_at,
        )
        if not touched:
            current = await self._sessions.get(session.session_id)
            if current is not None and current.replaced_by_session_id is not None:
                await self._revoke_successors(current.replaced_by_session_id, now=now)
                raise SessionDeniedError(SessionDenialReason.TOKEN_REUSE)
            raise SessionDeniedError(SessionDenialReason.INACTIVE)
        return ValidatedSession(refreshed, operator, tenant, membership)

    async def rotate(
        self,
        token: OpaqueSessionToken,
        *,
        now: datetime,
    ) -> IssuedSession:
        """Replace one active token and atomically revoke its predecessor."""
        validated = await self.validate(token, now=now)
        return await self._replace_validated(
            validated,
            now=now,
            active_tenant_id=validated.session.active_tenant_id,
        )

    async def select_tenant(
        self,
        token: OpaqueSessionToken,
        tenant_id: TenantId,
        *,
        now: datetime,
    ) -> IssuedSession:
        """Rotate a valid session into a currently authorized tenant boundary.

        @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
        """
        validated = await self.validate(token, now=now)
        return await self._replace_validated(
            validated,
            now=now,
            active_tenant_id=tenant_id,
        )

    async def _replace_validated(
        self,
        validated: ValidatedSession,
        *,
        now: datetime,
        active_tenant_id: TenantId | None,
    ) -> IssuedSession:
        successor = await self.issue(
            validated.operator.operator_id,
            now=now,
            active_tenant_id=active_tenant_id,
        )
        claimed = await self._sessions.revoke_if_active(
            validated.session.session_id,
            revoked_at=now,
            replaced_by_session_id=successor.session.session_id,
        )
        if not claimed:
            await self._sessions.delete(successor.session.session_id)
            current = await self._sessions.get(validated.session.session_id)
            if current is not None and current.replaced_by_session_id is not None:
                await self._revoke_successors(current.replaced_by_session_id, now=now)
                raise SessionDeniedError(SessionDenialReason.TOKEN_REUSE)
            raise SessionDeniedError(SessionDenialReason.ROTATION_CONFLICT)
        return successor

    async def logout(self, token: OpaqueSessionToken, *, now: datetime) -> AccessSession | None:
        """Idempotently revoke a token and return its non-secret session snapshot."""
        _require_utc(now)
        session = await self._sessions.get_by_digest(self._tokens.digest(token))
        if session is None:
            return None
        if session.replaced_by_session_id is not None:
            await self._revoke_successors(session.replaced_by_session_id, now=now)
        await self._sessions.revoke_if_active(session.session_id, revoked_at=now)
        return session

    async def _active_operator(
        self,
        operator_id: OperatorId,
        *,
        session_id: SessionId | None = None,
        now: datetime | None = None,
    ) -> Operator:
        operator = await self._operators.get(operator_id)
        if operator is None or operator.status is not OperatorStatus.ACTIVE:
            if session_id is not None and now is not None:
                await self._sessions.revoke_if_active(session_id, revoked_at=now)
            raise SessionDeniedError(SessionDenialReason.OPERATOR_INACTIVE)
        return operator

    async def _active_tenant_membership(
        self,
        operator_id: OperatorId,
        tenant_id: TenantId,
        *,
        session_id: SessionId | None = None,
        now: datetime | None = None,
    ) -> tuple[Tenant, Membership]:
        tenant = await self._tenants.get(tenant_id)
        if tenant is None or tenant.status is not TenantStatus.ACTIVE:
            if session_id is not None and now is not None:
                await self._sessions.revoke_if_active(session_id, revoked_at=now)
            raise SessionDeniedError(SessionDenialReason.TENANT_INACTIVE)
        membership = await self._memberships.get_for_operator_and_tenant(operator_id, tenant_id)
        if membership is None or membership.status is not MembershipStatus.ACTIVE:
            if session_id is not None and now is not None:
                await self._sessions.revoke_if_active(session_id, revoked_at=now)
            raise SessionDeniedError(SessionDenialReason.MEMBERSHIP_INACTIVE)
        return tenant, membership

    async def _revoke_successors(self, session_id: SessionId, *, now: datetime) -> None:
        current_id: SessionId | None = session_id
        for _ in range(64):
            if current_id is None:
                return
            current = await self._sessions.get(current_id)
            if current is None:
                return
            await self._sessions.revoke_if_active(current_id, revoked_at=now)
            current_id = current.replaced_by_session_id
        raise RuntimeError("session replacement chain exceeds safety limit")


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("session time must be a timezone-aware UTC datetime")
