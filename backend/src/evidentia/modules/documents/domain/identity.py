"""Opaque identities and safe source-document values.

@skyhook-implements REQ-001
@skyhook-implements NFR-002
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID, uuid4

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _canonical_uuid(value: str, label: str) -> str:
    try:
        return str(UUID(value))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a valid UUID") from error


@dataclass(frozen=True, slots=True)
class DocumentId:
    """Server-issued identity for one immutable document-custody root.

    @skyhook-implements REQ-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _canonical_uuid(self.value, "document ID"))

    @classmethod
    def new(cls) -> DocumentId:
        """Create a new server-owned document identity."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class UploadAttemptId:
    """Server-issued identity for one observable preservation attempt.

    @skyhook-implements REQ-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _canonical_uuid(self.value, "upload attempt ID"))

    @classmethod
    def new(cls) -> UploadAttemptId:
        """Create a new server-owned upload-attempt identity."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class Sha256Digest:
    """Canonical SHA-256 integrity digest for preserved bytes.

    @skyhook-implements REQ-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _SHA256.fullmatch(self.value) is None:
            raise ValueError("SHA-256 digest must contain 64 lower-case hexadecimal characters")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class OriginalFilename:
    """Display-only source filename that can never become a storage path.

    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValueError("original filename must be a string")
        normalized = unicodedata.normalize("NFKC", self.value)
        if (
            not normalized
            or normalized != normalized.strip()
            or len(normalized) > 255
            or "/" in normalized
            or "\\" in normalized
            or normalized in {".", ".."}
            or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
        ):
            raise ValueError("original filename must be a safe 1 to 255 character display name")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class MediaType:
    """Normalized declared media type without transport parameters.

    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValueError("media type must be a string")
        normalized = self.value.strip().casefold()
        if len(normalized) > 255 or _MEDIA_TYPE.fullmatch(normalized) is None:
            raise ValueError("media type must be a valid type/subtype value")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class IdempotencyKey:
    """Opaque client retry key scoped by the trusted tenant.

    @skyhook-implements NFR-001
    @skyhook-implements NFR-002
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _IDEMPOTENCY_KEY.fullmatch(self.value) is None:
            raise ValueError("idempotency key must contain 1 to 128 safe opaque characters")

    def __str__(self) -> str:
        return self.value
