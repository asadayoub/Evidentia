"""Opaque identities and normalized machine-readable access values.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID, uuid4

_LOCAL_PART = re.compile(r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TENANT_SLUG = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_MACHINE_SEGMENT = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical_uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("identifier must be a valid UUID") from error
    return str(parsed)


def _require_safe_text(value: str, label: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    normalized = unicodedata.normalize("NFKC", value)
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{label} must contain 1 to {maximum} characters")
    if normalized != normalized.strip():
        raise ValueError(f"{label} must not contain outer whitespace")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValueError(f"{label} must not contain control characters")
    return normalized


@dataclass(frozen=True, slots=True)
class OperatorId:
    """Opaque stable identity for a human or service operator.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _canonical_uuid(self.value))

    @classmethod
    def new(cls) -> OperatorId:
        """Create a new opaque operator identity."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TenantId:
    """Opaque stable identity for one tenant security boundary.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _canonical_uuid(self.value))

    @classmethod
    def new(cls) -> TenantId:
        """Create a new opaque tenant identity."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MembershipId:
    """Opaque identity for one operator-to-tenant membership.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _canonical_uuid(self.value))

    @classmethod
    def new(cls) -> MembershipId:
        """Create a new opaque membership identity."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CredentialId:
    """Opaque identity for a provider-owned authentication credential.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _canonical_uuid(self.value))

    @classmethod
    def new(cls) -> CredentialId:
        """Create a new opaque credential identity."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SessionId:
    """Opaque identity for a revocable authenticated session.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _canonical_uuid(self.value))

    @classmethod
    def new(cls) -> SessionId:
        """Create a new opaque session identity."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class LoginIdentifier:
    """Canonical local login address independent of an identity provider.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValueError("login identifier must be a string")
        normalized = unicodedata.normalize("NFKC", self.value).strip().casefold()
        if (
            not normalized
            or len(normalized) > 254
            or any(character.isspace() for character in normalized)
        ):
            raise ValueError("login identifier must be a valid normalized email address")
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ValueError("login identifier must not contain control characters")
        if normalized.count("@") != 1:
            raise ValueError("login identifier must be a valid normalized email address")
        local, domain = normalized.split("@")
        labels = domain.split(".")
        if (
            not local
            or len(local) > 64
            or _LOCAL_PART.fullmatch(local) is None
            or local.startswith(".")
            or local.endswith(".")
            or ".." in local
            or not domain
            or len(domain) > 253
            or any(_DOMAIN_LABEL.fullmatch(label) is None for label in labels)
        ):
            raise ValueError("login identifier must be a valid normalized email address")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class TenantSlug:
    """Stable lower-kebab-case tenant name used in URLs and configuration.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or len(self.value) > 63
            or _TENANT_SLUG.fullmatch(self.value) is None
        ):
            raise ValueError("tenant slug must be 1 to 63 lower-kebab-case characters")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class Capability:
    """Namespaced permission key granted through a tenant membership.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or len(self.value) > 128:
            raise ValueError("capability must be a namespaced lower-case machine key")
        segments = self.value.split(".")
        if len(segments) < 2 or any(_MACHINE_SEGMENT.fullmatch(item) is None for item in segments):
            raise ValueError("capability must be a namespaced lower-case machine key")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class IdentityProviderKey:
    """Stable machine key for a local or external identity provider.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _MACHINE_SEGMENT.fullmatch(self.value) is None:
            raise ValueError("identity provider key must be a lower-snake-case machine key")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class ProviderSubject:
    """Opaque provider-issued subject retained without case normalization.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _require_safe_text(self.value, "provider subject", maximum=512),
        )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class SessionTokenDigest:
    """Lowercase SHA-256 digest used to locate an opaque session token.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _SHA256.fullmatch(self.value) is None:
            raise ValueError("session token digest must be a lowercase SHA-256 value")

    def __str__(self) -> str:
        return self.value
