"""Trusted request-context construction and fail-closed capability checks.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from evidentia.modules.access.domain.identity import (
    Capability,
    MembershipId,
    OperatorId,
    SessionId,
    TenantId,
)
from evidentia.modules.access.domain.models import (
    AccessSession,
    Membership,
    MembershipStatus,
    Operator,
    OperatorStatus,
    Tenant,
    TenantStatus,
)


class AccessDenialReason(StrEnum):
    """Stable, non-sensitive reason codes for authentication and authorization denial.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    SESSION_INACTIVE = "session_inactive"
    SESSION_OPERATOR_MISMATCH = "session_operator_mismatch"
    OPERATOR_DISABLED = "operator_disabled"
    TENANT_UNAVAILABLE = "tenant_unavailable"
    MEMBERSHIP_INACTIVE = "membership_inactive"
    MEMBERSHIP_OPERATOR_MISMATCH = "membership_operator_mismatch"
    MEMBERSHIP_TENANT_MISMATCH = "membership_tenant_mismatch"
    CAPABILITY_REQUIRED = "capability_required"
    INVALID_CONTEXT = "invalid_context"


class AccessDeniedError(PermissionError):
    """Typed fail-closed denial safe for translation at an interface boundary.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(
        self,
        reason: AccessDenialReason,
        *,
        required_capability: Capability | None = None,
    ) -> None:
        if not isinstance(reason, AccessDenialReason):
            raise ValueError("access denial reason must be an AccessDenialReason")
        if required_capability is not None and not isinstance(required_capability, Capability):
            raise ValueError("required capability must be a Capability")
        self.reason = reason
        self.required_capability = required_capability
        super().__init__(reason.value)


@dataclass(frozen=True, slots=True)
class TrustedRequestContext:
    """Verified operator, tenant, membership, session, and capability context.

    Construction is restricted to ``build_trusted_context`` so downstream modules
    never need to trust client-provided identity or tenant headers.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    operator_id: OperatorId
    tenant_id: TenantId
    membership_id: MembershipId
    session_id: SessionId
    capabilities: frozenset[Capability]
    correlation_id: str
    authenticated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.operator_id, OperatorId):
            raise ValueError("trusted context operator must be an OperatorId")
        if not isinstance(self.tenant_id, TenantId):
            raise ValueError("trusted context tenant must be a TenantId")
        if not isinstance(self.membership_id, MembershipId):
            raise ValueError("trusted context membership must be a MembershipId")
        if not isinstance(self.session_id, SessionId):
            raise ValueError("trusted context session must be a SessionId")
        if not isinstance(self.capabilities, frozenset) or not all(
            isinstance(item, Capability) for item in self.capabilities
        ):
            raise ValueError("trusted context capabilities must be an immutable Capability set")
        if (
            not isinstance(self.correlation_id, str)
            or not self.correlation_id
            or self.correlation_id != self.correlation_id.strip()
            or len(self.correlation_id) > 128
            or any(character.isspace() for character in self.correlation_id)
            or any(
                ord(character) < 32 or ord(character) == 127 for character in self.correlation_id
            )
        ):
            raise ValueError("correlation ID must be 1 to 128 non-whitespace characters")
        if (
            not isinstance(self.authenticated_at, datetime)
            or self.authenticated_at.tzinfo is None
            or self.authenticated_at.utcoffset() != UTC.utcoffset(self.authenticated_at)
        ):
            raise ValueError("trusted context authenticated_at must be a UTC datetime")

    def has_capability(self, capability: Capability) -> bool:
        """Return whether the verified membership grants ``capability``."""
        return capability in self.capabilities

    def require_capability(self, capability: Capability) -> None:
        """Fail closed when the verified membership lacks ``capability``."""
        if not self.has_capability(capability):
            raise AccessDeniedError(
                AccessDenialReason.CAPABILITY_REQUIRED,
                required_capability=capability,
            )


def build_trusted_context(
    *,
    session: AccessSession,
    operator: Operator,
    tenant: Tenant,
    membership: Membership,
    correlation_id: str,
    now: datetime,
) -> TrustedRequestContext:
    """Validate current access state and create the only trusted context contract.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != UTC.utcoffset(now):
        raise AccessDeniedError(AccessDenialReason.INVALID_CONTEXT)
    if session.operator_id != operator.operator_id:
        raise AccessDeniedError(AccessDenialReason.SESSION_OPERATOR_MISMATCH)
    if not session.is_active_at(now):
        raise AccessDeniedError(AccessDenialReason.SESSION_INACTIVE)
    if operator.status is not OperatorStatus.ACTIVE:
        raise AccessDeniedError(AccessDenialReason.OPERATOR_DISABLED)
    if tenant.status is not TenantStatus.ACTIVE:
        raise AccessDeniedError(AccessDenialReason.TENANT_UNAVAILABLE)
    if membership.operator_id != operator.operator_id:
        raise AccessDeniedError(AccessDenialReason.MEMBERSHIP_OPERATOR_MISMATCH)
    if membership.tenant_id != tenant.tenant_id:
        raise AccessDeniedError(AccessDenialReason.MEMBERSHIP_TENANT_MISMATCH)
    if membership.status is not MembershipStatus.ACTIVE:
        raise AccessDeniedError(AccessDenialReason.MEMBERSHIP_INACTIVE)
    try:
        return TrustedRequestContext(
            operator_id=operator.operator_id,
            tenant_id=tenant.tenant_id,
            membership_id=membership.membership_id,
            session_id=session.session_id,
            capabilities=membership.capabilities,
            correlation_id=correlation_id,
            authenticated_at=session.authenticated_at,
        )
    except ValueError as error:
        raise AccessDeniedError(AccessDenialReason.INVALID_CONTEXT) from error
