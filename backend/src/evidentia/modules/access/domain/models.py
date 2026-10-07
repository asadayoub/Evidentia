"""Immutable Access and Tenancy domain snapshots.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from evidentia.modules.access.domain.identity import (
    Capability,
    CredentialId,
    IdentityProviderKey,
    LoginIdentifier,
    MembershipId,
    OperatorId,
    ProviderSubject,
    SessionId,
    TenantId,
    TenantSlug,
)


def _require_utc(value: datetime, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(value)
    ):
        raise ValueError(f"{label} must be a timezone-aware UTC datetime")


def _require_display_text(value: str, label: str, maximum: int) -> None:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must contain 1 to {maximum} non-padding characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{label} must not contain control characters")


class OperatorStatus(StrEnum):
    """Security state of an operator account.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    ACTIVE = "active"
    DISABLED = "disabled"


class TenantStatus(StrEnum):
    """Security state of a tenant boundary.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    ACTIVE = "active"
    SUSPENDED = "suspended"


class MembershipStatus(StrEnum):
    """Lifecycle state of one operator-to-tenant relationship.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class Operator:
    """Provider-independent operator identity and security state.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    operator_id: OperatorId
    login_identifier: LoginIdentifier
    display_name: str
    status: OperatorStatus = OperatorStatus.ACTIVE

    def __post_init__(self) -> None:
        if not isinstance(self.operator_id, OperatorId):
            raise ValueError("operator identity must be an OperatorId")
        if not isinstance(self.login_identifier, LoginIdentifier):
            raise ValueError("operator login identifier must be a LoginIdentifier")
        _require_display_text(self.display_name, "operator display name", 200)
        if not isinstance(self.status, OperatorStatus):
            raise ValueError("operator status must be an OperatorStatus")


@dataclass(frozen=True, slots=True)
class Tenant:
    """Tenant identity and availability state shared by all deployment modes.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    tenant_id: TenantId
    slug: TenantSlug
    display_name: str
    status: TenantStatus = TenantStatus.ACTIVE

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, TenantId):
            raise ValueError("tenant identity must be a TenantId")
        if not isinstance(self.slug, TenantSlug):
            raise ValueError("tenant slug must be a TenantSlug")
        _require_display_text(self.display_name, "tenant display name", 200)
        if not isinstance(self.status, TenantStatus):
            raise ValueError("tenant status must be a TenantStatus")


@dataclass(frozen=True, slots=True)
class Membership:
    """Tenant-scoped capability grants for one operator.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    membership_id: MembershipId
    tenant_id: TenantId
    operator_id: OperatorId
    capabilities: frozenset[Capability]
    status: MembershipStatus = MembershipStatus.ACTIVE

    def __post_init__(self) -> None:
        if not isinstance(self.membership_id, MembershipId):
            raise ValueError("membership identity must be a MembershipId")
        if not isinstance(self.tenant_id, TenantId):
            raise ValueError("membership tenant identity must be a TenantId")
        if not isinstance(self.operator_id, OperatorId):
            raise ValueError("membership operator identity must be an OperatorId")
        if not isinstance(self.capabilities, frozenset) or not all(
            isinstance(item, Capability) for item in self.capabilities
        ):
            raise ValueError("membership capabilities must be an immutable Capability set")
        if not isinstance(self.status, MembershipStatus):
            raise ValueError("membership status must be a MembershipStatus")

    def grants(self, capability: Capability) -> bool:
        """Return whether this active membership contains ``capability``."""
        return self.status is MembershipStatus.ACTIVE and capability in self.capabilities


@dataclass(frozen=True, slots=True)
class CredentialIdentity:
    """Provider mapping identity without secret or password-hash material.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    credential_id: CredentialId
    operator_id: OperatorId
    provider: IdentityProviderKey
    subject: ProviderSubject

    def __post_init__(self) -> None:
        if not isinstance(self.credential_id, CredentialId):
            raise ValueError("credential identity must be a CredentialId")
        if not isinstance(self.operator_id, OperatorId):
            raise ValueError("credential operator identity must be an OperatorId")
        if not isinstance(self.provider, IdentityProviderKey):
            raise ValueError("credential provider must be an IdentityProviderKey")
        if not isinstance(self.subject, ProviderSubject):
            raise ValueError("credential subject must be a ProviderSubject")


@dataclass(frozen=True, slots=True)
class AccessSession:
    """Revocable session metadata that never contains the raw bearer token.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    session_id: SessionId
    operator_id: OperatorId
    authenticated_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, SessionId):
            raise ValueError("session identity must be a SessionId")
        if not isinstance(self.operator_id, OperatorId):
            raise ValueError("session operator identity must be an OperatorId")
        _require_utc(self.authenticated_at, "session authenticated_at")
        _require_utc(self.last_seen_at, "session last_seen_at")
        _require_utc(self.expires_at, "session expires_at")
        if self.revoked_at is not None:
            _require_utc(self.revoked_at, "session revoked_at")
        if self.last_seen_at < self.authenticated_at:
            raise ValueError("session last_seen_at cannot precede authentication")
        if self.expires_at <= self.authenticated_at:
            raise ValueError("session expiry must follow authentication")
        if self.revoked_at is not None and self.revoked_at < self.authenticated_at:
            raise ValueError("session revocation cannot precede authentication")

    def is_active_at(self, instant: datetime) -> bool:
        """Return whether the session is unrevoked and unexpired at ``instant``."""
        _require_utc(instant, "session evaluation instant")
        return self.revoked_at is None and instant < self.expires_at
