"""Immutable published module and schema-version aggregate snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field

from evidentia.modules.schemas.domain.artifact_links import ArtifactBindings
from evidentia.modules.schemas.domain.definitions import FieldDefinition, ensure_unique_root_fields
from evidentia.modules.schemas.domain.identity import (
    FieldKey,
    ReleaseLabel,
    SchemaId,
    SchemaModuleId,
    SchemaVersion,
)
from evidentia.modules.schemas.domain.lifecycle import SchemaLifecycleState

_IMMUTABLE_STATES = frozenset(
    {
        SchemaLifecycleState.PUBLISHED,
        SchemaLifecycleState.DEPRECATED,
        SchemaLifecycleState.RETIRED,
    }
)


@dataclass(frozen=True, slots=True)
class SchemaModuleReference:
    """Stable reference to one immutable schema-module version.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    module_id: SchemaModuleId
    version: SchemaVersion

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, SchemaModuleId):
            raise ValueError("module reference identity must use SchemaModuleId")
        if not isinstance(self.version, SchemaVersion):
            raise ValueError("module reference version must use SchemaVersion")


@dataclass(frozen=True, slots=True)
class PublishedSchemaModule:
    """Reusable immutable tree of fields from a published module version.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    module_id: SchemaModuleId
    version: SchemaVersion
    key: FieldKey
    fields: tuple[FieldDefinition, ...]
    lifecycle: SchemaLifecycleState = SchemaLifecycleState.PUBLISHED
    release_label: ReleaseLabel | None = None
    artifacts: ArtifactBindings = field(default_factory=ArtifactBindings)

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, SchemaModuleId):
            raise ValueError("published module identity must use SchemaModuleId")
        if not isinstance(self.version, SchemaVersion):
            raise ValueError("published module version must use SchemaVersion")
        if not isinstance(self.key, FieldKey):
            raise ValueError("published module key must use FieldKey")
        if self.lifecycle not in _IMMUTABLE_STATES:
            raise ValueError("published module cannot reference mutable draft content")
        if not isinstance(self.fields, tuple):
            raise ValueError("published module fields must be retained in an immutable tuple")
        if not self.fields:
            raise ValueError("published module must contain at least one root field")
        ensure_unique_root_fields(self.fields)
        if self.release_label is not None and not isinstance(self.release_label, ReleaseLabel):
            raise ValueError("published module release label must use ReleaseLabel")
        if not isinstance(self.artifacts, ArtifactBindings):
            raise ValueError("published module artifacts must use ArtifactBindings")

    @property
    def reference(self) -> SchemaModuleReference:
        """Return the stable identity and version used by composition records."""
        return SchemaModuleReference(self.module_id, self.version)


@dataclass(frozen=True, slots=True)
class PublishedSchemaVersion:
    """Immutable schema snapshot retaining every selected module version.

    This aggregate records inputs but does not merge module fields. Deterministic
    composition and conflict reporting belong to the next implementation pass.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    schema_id: SchemaId
    version: SchemaVersion
    fields: tuple[FieldDefinition, ...] = ()
    modules: tuple[PublishedSchemaModule, ...] = ()
    lifecycle: SchemaLifecycleState = SchemaLifecycleState.PUBLISHED
    release_label: ReleaseLabel | None = None
    artifacts: ArtifactBindings = field(default_factory=ArtifactBindings)

    def __post_init__(self) -> None:
        if not isinstance(self.schema_id, SchemaId):
            raise ValueError("published schema identity must use SchemaId")
        if not isinstance(self.version, SchemaVersion):
            raise ValueError("published schema version must use SchemaVersion")
        if self.lifecycle not in _IMMUTABLE_STATES:
            raise ValueError("published schema cannot reference mutable draft content")
        if not isinstance(self.fields, tuple) or not isinstance(self.modules, tuple):
            raise ValueError("published schema content must be retained in immutable tuples")
        if not self.fields and not self.modules:
            raise ValueError("published schema must contain fields, modules, or both")
        ensure_unique_root_fields(self.fields)
        if not all(isinstance(module, PublishedSchemaModule) for module in self.modules):
            raise ValueError("published schema modules must be immutable module snapshots")
        references = [module.reference for module in self.modules]
        if len(set(references)) != len(references):
            raise ValueError("published schema must not repeat a module version")
        if self.release_label is not None and not isinstance(self.release_label, ReleaseLabel):
            raise ValueError("published schema release label must use ReleaseLabel")
        if not isinstance(self.artifacts, ArtifactBindings):
            raise ValueError("published schema artifacts must use ArtifactBindings")

    @property
    def module_references(self) -> tuple[SchemaModuleReference, ...]:
        """Return selected module identities in deterministic declared order."""
        return tuple(module.reference for module in self.modules)
