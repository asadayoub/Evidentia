"""Stable identities and machine-readable names for schema definitions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

_MACHINE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def _canonical_uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("identifier must be a valid UUID") from error
    return str(parsed)


@dataclass(frozen=True, slots=True)
class SchemaId:
    """Opaque stable identity for a schema family.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _canonical_uuid(self.value))

    @classmethod
    def new(cls) -> SchemaId:
        """Create a new opaque schema identity."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SchemaModuleId:
    """Opaque stable identity for a reusable schema module.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _canonical_uuid(self.value))

    @classmethod
    def new(cls) -> SchemaModuleId:
        """Create a new opaque schema-module identity."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class SchemaVersion:
    """Positive monotonic version number within one stable identity.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 1:
            raise ValueError("schema version must be a positive integer")

    def next(self) -> SchemaVersion:
        """Return the immediately following monotonic version."""
        return SchemaVersion(self.value + 1)

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class ReleaseLabel:
    """Optional human-facing label that never replaces machine version identity.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValueError("release label must be a string")
        if not self.value or self.value != self.value.strip() or len(self.value) > 64:
            raise ValueError("release label must contain 1 to 64 non-padding characters")
        if any(ord(character) < 32 or ord(character) == 127 for character in self.value):
            raise ValueError("release label must not contain control characters")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class FieldKey:
    """Stable language-neutral lower-snake-case key for one field segment.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _MACHINE_KEY_PATTERN.fullmatch(self.value):
            raise ValueError("field key must be a lower-snake-case machine key")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class FieldPath:
    """Immutable path composed of stable field-key segments.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    segments: tuple[FieldKey, ...]

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("field path must contain at least one segment")
        if not all(isinstance(segment, FieldKey) for segment in self.segments):
            raise ValueError("field path segments must be FieldKey values")

    @classmethod
    def parse(cls, value: str) -> FieldPath:
        """Parse a dot-separated machine path without silently normalizing it."""
        if not isinstance(value, str) or not value:
            raise ValueError("field path must be a non-empty string")
        return cls(tuple(FieldKey(segment) for segment in value.split(".")))

    def child(self, key: FieldKey) -> FieldPath:
        """Return a new path with one validated child segment."""
        return FieldPath((*self.segments, key))

    def __str__(self) -> str:
        return ".".join(str(segment) for segment in self.segments)
