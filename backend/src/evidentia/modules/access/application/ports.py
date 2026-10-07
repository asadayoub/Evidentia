"""Provider- and persistence-independent Access and Tenancy ports.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, TypeVar

from evidentia.modules.access.domain.identity import (
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
    Operator,
    Tenant,
)

_CredentialT_contra = TypeVar("_CredentialT_contra", contravariant=True)


class AuthenticationSecret:
    """Short-lived authentication material whose representations are always redacted.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError("authentication secret must be a non-empty string")
        self.__value = value

    def reveal(self) -> str:
        """Reveal the secret only to the provider adapter that must verify it."""
        return self.__value

    def __repr__(self) -> str:
        return "AuthenticationSecret('<redacted>')"

    def __str__(self) -> str:
        return "<redacted>"


class OpaqueSessionToken:
    """High-entropy bearer token kept out of domain snapshots and persistence ports.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or len(value) < 32:
            raise ValueError("opaque session token must contain at least 32 characters")
        if any(
            character.isspace() or ord(character) < 33 or ord(character) == 127
            for character in value
        ):
            raise ValueError(
                "opaque session token must not contain whitespace or control characters"
            )
        self.__value = value

    def reveal(self) -> str:
        """Reveal the token only at the cookie or digest boundary."""
        return self.__value

    def __repr__(self) -> str:
        return "OpaqueSessionToken('<redacted>')"

    def __str__(self) -> str:
        return "<redacted>"


class Argon2idPasswordHash:
    """Encoded Argon2id verifier kept redacted outside credential adapters.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        if (
            not isinstance(value, str)
            or not value.startswith("$argon2id$")
            or len(value) > 1024
            or any(character.isspace() for character in value)
        ):
            raise ValueError("password hash must be a valid encoded Argon2id value")
        self.__value = value

    def reveal(self) -> str:
        """Reveal the encoded verifier only at hashing or persistence boundaries."""
        return self.__value

    def __repr__(self) -> str:
        return "Argon2idPasswordHash('<redacted>')"

    def __str__(self) -> str:
        return "<redacted>"


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    """Provider result that binds a verified credential to an operator.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    operator_id: OperatorId
    credential_id: CredentialId
    provider: IdentityProviderKey
    subject: ProviderSubject
    authenticated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.operator_id, OperatorId):
            raise ValueError("authenticated operator identity must be an OperatorId")
        if not isinstance(self.credential_id, CredentialId):
            raise ValueError("authenticated credential identity must be a CredentialId")
        if not isinstance(self.provider, IdentityProviderKey):
            raise ValueError("authenticated provider must be an IdentityProviderKey")
        if not isinstance(self.subject, ProviderSubject):
            raise ValueError("authenticated subject must be a ProviderSubject")
        if (
            not isinstance(self.authenticated_at, datetime)
            or self.authenticated_at.tzinfo is None
            or self.authenticated_at.utcoffset() != UTC.utcoffset(self.authenticated_at)
        ):
            raise ValueError("authenticated identity timestamp must be a UTC datetime")


class IdentityProvider(Protocol[_CredentialT_contra]):
    """Replaceable provider contract for local credentials or future OIDC proofs.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    async def authenticate(
        self,
        credential: _CredentialT_contra,
        *,
        now: datetime,
    ) -> AuthenticatedIdentity | None:
        """Verify provider-specific material without leaking it into the domain."""
        ...


class SessionTokenProvider(Protocol):
    """Port for issuing and hashing opaque browser-session tokens.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def issue(self) -> OpaqueSessionToken:
        """Issue a new high-entropy bearer token."""
        ...

    def digest(self, token: OpaqueSessionToken) -> SessionTokenDigest:
        """Produce the only token representation allowed in persistence."""
        ...


class PasswordHasher(Protocol):
    """Port for producing and verifying encoded Argon2id password hashes.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def hash(self, secret: AuthenticationSecret) -> Argon2idPasswordHash:
        """Hash a plaintext secret with a library-generated random salt."""
        ...

    def verify(
        self,
        password_hash: Argon2idPasswordHash | None,
        secret: AuthenticationSecret,
    ) -> bool:
        """Verify a hash or perform equivalent dummy work when it is absent."""
        ...


class AuthenticationThrottle(Protocol):
    """Replaceable bounded backoff for authentication failures.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    async def retry_after_seconds(self, key: LoginIdentifier, *, now: datetime) -> int:
        """Return a bounded delay remaining for a normalized identifier."""
        ...

    async def record_failure(self, key: LoginIdentifier, *, now: datetime) -> int:
        """Record a failure and return the newly applicable bounded delay."""
        ...

    async def clear(self, key: LoginIdentifier) -> None:
        """Clear transient failure state after successful authentication."""
        ...


class OperatorRepository(Protocol):
    """Transaction-neutral persistence port for operators.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    async def add(self, operator: Operator) -> None:
        """Stage a new operator in the caller-owned transaction."""
        ...

    async def get(self, operator_id: OperatorId) -> Operator | None:
        """Load an operator by opaque identity."""
        ...

    async def get_by_login_identifier(self, login_identifier: LoginIdentifier) -> Operator | None:
        """Load an operator by canonical login identifier."""
        ...


class TenantRepository(Protocol):
    """Transaction-neutral persistence port for tenant boundaries.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    async def add(self, tenant: Tenant) -> None:
        """Stage a new tenant in the caller-owned transaction."""
        ...

    async def get(self, tenant_id: TenantId) -> Tenant | None:
        """Load a tenant by opaque identity."""
        ...

    async def get_by_slug(self, slug: TenantSlug) -> Tenant | None:
        """Load a tenant by stable machine slug."""
        ...


class MembershipRepository(Protocol):
    """Transaction-neutral persistence port for tenant memberships.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    async def add(self, membership: Membership) -> None:
        """Stage a new membership in the caller-owned transaction."""
        ...

    async def get(self, membership_id: MembershipId) -> Membership | None:
        """Load a membership by opaque identity."""
        ...

    async def get_for_operator_and_tenant(
        self,
        operator_id: OperatorId,
        tenant_id: TenantId,
    ) -> Membership | None:
        """Load the exact relationship used to establish tenant context."""
        ...

    async def list_for_operator(self, operator_id: OperatorId) -> tuple[Membership, ...]:
        """List memberships visible to one operator."""
        ...


class CredentialRepository(Protocol):
    """Provider-neutral mappings with optional local Argon2id material.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    async def add(
        self,
        credential: CredentialIdentity,
        password_hash: Argon2idPasswordHash | None = None,
    ) -> None:
        """Stage a provider mapping and optional local password verifier."""
        ...

    async def get_by_provider_subject(
        self,
        provider: IdentityProviderKey,
        subject: ProviderSubject,
    ) -> CredentialIdentity | None:
        """Load the unique mapping for a provider-issued subject."""
        ...

    async def get_local_password_hash(
        self, credential_id: CredentialId
    ) -> Argon2idPasswordHash | None:
        """Load a redacted local verifier wrapper."""
        ...

    async def replace_local_password_hash(
        self,
        credential_id: CredentialId,
        password_hash: Argon2idPasswordHash,
    ) -> None:
        """Rotate local verification material in the caller transaction."""
        ...


class SessionRepository(Protocol):
    """Transaction-neutral persistence port that accepts only token digests.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    async def add(self, session: AccessSession, token_digest: SessionTokenDigest) -> None:
        """Stage a new session and its non-reversible token digest."""
        ...

    async def get_by_digest(self, token_digest: SessionTokenDigest) -> AccessSession | None:
        """Load a session without accepting or returning the raw token."""
        ...

    async def replace(self, session: AccessSession) -> None:
        """Persist current expiry, last-use, or revocation metadata."""
        ...

    async def get(self, session_id: SessionId) -> AccessSession | None:
        """Load a session for administrative revocation."""
        ...

    async def revoke_if_active(
        self,
        session_id: SessionId,
        *,
        revoked_at: datetime,
        replaced_by_session_id: SessionId | None = None,
    ) -> bool:
        """Atomically claim an unrevoked session for logout or rotation."""
        ...

    async def delete(self, session_id: SessionId) -> None:
        """Delete an uncommitted successor after a lost rotation race."""
        ...

    async def touch_if_active(
        self,
        session_id: SessionId,
        *,
        last_seen_at: datetime,
        expires_at: datetime,
    ) -> bool:
        """Atomically refresh an unrevoked session without resurrecting it."""
        ...
