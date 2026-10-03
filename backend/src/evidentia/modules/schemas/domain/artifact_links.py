"""Version-specific links from data shape to separately governed artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from evidentia.modules.schemas.domain.identity import SchemaVersion

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SchemaArtifactKind(StrEnum):
    """Concern kept separate from a canonical schema's data shape.

    @skyhook-implements REQ-003
    @skyhook-implements REQ-005
    @skyhook-implements REQ-006
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    VALIDATION_RULES = "validation_rules"
    NORMALIZATION_RULES = "normalization_rules"
    PRESENTATION_HINTS = "presentation_hints"
    LOCALIZATION = "localization"
    EXTRACTION_HINTS = "extraction_hints"
    EVIDENCE_EXPECTATION = "evidence_expectation"


@dataclass(frozen=True, slots=True)
class PublishedArtifactReference:
    """Immutable reference to one published auxiliary artifact version.

    The type intentionally cannot represent an unversioned or mutable draft
    artifact. The retained digest lets loaders detect a missing or substituted
    artifact before using the schema snapshot.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    artifact_id: str
    version: SchemaVersion
    kind: SchemaArtifactKind
    content_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str):
            raise ValueError("artifact identity must be a UUID string")
        try:
            canonical_id = str(UUID(self.artifact_id))
        except ValueError as error:
            raise ValueError("artifact identity must be a valid UUID") from error
        if not isinstance(self.version, SchemaVersion):
            raise ValueError("artifact reference must contain an explicit schema version")
        if not isinstance(self.kind, SchemaArtifactKind):
            raise ValueError("artifact reference must declare a recognized artifact kind")
        if (
            not isinstance(self.content_sha256, str)
            or _SHA256_PATTERN.fullmatch(self.content_sha256) is None
        ):
            raise ValueError("artifact content digest must be lowercase SHA-256 hexadecimal")
        object.__setattr__(self, "artifact_id", canonical_id)


@dataclass(frozen=True, slots=True)
class ArtifactBindings:
    """Immutable set of explicit artifact versions bound to a schema node.

    @skyhook-implements REQ-003
    @skyhook-implements REQ-005
    @skyhook-implements REQ-006
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    references: tuple[PublishedArtifactReference, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.references, tuple):
            raise ValueError("artifact bindings must retain references in an immutable tuple")
        if not all(
            isinstance(reference, PublishedArtifactReference) for reference in self.references
        ):
            raise ValueError("artifact bindings may contain only published artifact references")
        identities = [
            (reference.artifact_id, reference.version.value, reference.kind)
            for reference in self.references
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("artifact bindings must not contain duplicate version references")

    def for_kind(self, kind: SchemaArtifactKind) -> tuple[PublishedArtifactReference, ...]:
        """Return references of one concern in their declared deterministic order."""
        return tuple(reference for reference in self.references if reference.kind is kind)
