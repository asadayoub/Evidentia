"""Deterministic compatibility analysis for immutable schema versions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from evidentia.modules.schemas.domain.definitions import FieldDefinition
from evidentia.modules.schemas.domain.identity import FieldPath
from evidentia.modules.schemas.domain.modules import PublishedSchemaVersion


class CompatibilityLevel(StrEnum):
    """Impact of adopting a candidate schema version.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    ADDITIVE_COMPATIBLE = "additive_compatible"
    BEHAVIOR_CHANGING = "behavior_changing"
    BREAKING = "breaking"


class SchemaChangeCode(StrEnum):
    """Stable code for one material schema evolution.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    OPTIONAL_FIELD_ADDED = "optional_field_added"
    REQUIRED_FIELD_ADDED = "required_field_added"
    FIELD_REMOVED = "field_removed"
    TYPE_CHANGED = "type_changed"
    CARDINALITY_TIGHTENED = "cardinality_tightened"
    CARDINALITY_RELAXED = "cardinality_relaxed"
    CONSTRAINT_CHANGED = "constraint_changed"
    ARTIFACT_BINDING_CHANGED = "artifact_binding_changed"
    MODULE_SELECTION_CHANGED = "module_selection_changed"


@dataclass(frozen=True, slots=True)
class SchemaChange:
    """One path-specific, explainable compatibility change.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    code: SchemaChangeCode
    level: CompatibilityLevel
    path: FieldPath | None
    message: str


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    """Deterministically ordered compatibility result.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    level: CompatibilityLevel
    changes: tuple[SchemaChange, ...]

    @property
    def requires_acknowledgement(self) -> bool:
        """Return whether publication needs an explicit risk acknowledgement."""
        return self.level is not CompatibilityLevel.ADDITIVE_COMPATIBLE


def compare_schema_versions(
    previous: PublishedSchemaVersion, candidate: PublishedSchemaVersion
) -> CompatibilityReport:
    """Classify all material differences between consecutive schema snapshots.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """
    if previous.schema_id != candidate.schema_id:
        raise ValueError("compatibility requires versions from the same schema family")
    if candidate.version.value <= previous.version.value:
        raise ValueError("candidate schema version must follow the previous version")

    changes = list(_compare_fields(previous.fields, candidate.fields))
    if previous.module_references != candidate.module_references:
        changes.append(
            SchemaChange(
                SchemaChangeCode.MODULE_SELECTION_CHANGED,
                CompatibilityLevel.BEHAVIOR_CHANGING,
                None,
                "selected schema module versions changed",
            )
        )
    if previous.artifacts != candidate.artifacts:
        changes.append(
            SchemaChange(
                SchemaChangeCode.ARTIFACT_BINDING_CHANGED,
                CompatibilityLevel.BEHAVIOR_CHANGING,
                None,
                "schema-level artifact bindings changed",
            )
        )
    ordered = tuple(sorted(changes, key=_change_sort_key))
    level = max(
        (change.level for change in ordered),
        key=_level_rank,
        default=CompatibilityLevel.ADDITIVE_COMPATIBLE,
    )
    return CompatibilityReport(level, ordered)


def _compare_fields(
    previous: tuple[FieldDefinition, ...], candidate: tuple[FieldDefinition, ...]
) -> tuple[SchemaChange, ...]:
    old = {path: field for root in previous for path, field in _flatten(root)}
    new = {path: field for root in candidate for path, field in _flatten(root)}
    changes: list[SchemaChange] = []
    for path in sorted(old.keys() | new.keys(), key=str):
        before, after = old.get(path), new.get(path)
        if before is None and after is not None:
            required = after.cardinality.required
            changes.append(
                SchemaChange(
                    SchemaChangeCode.REQUIRED_FIELD_ADDED
                    if required
                    else SchemaChangeCode.OPTIONAL_FIELD_ADDED,
                    CompatibilityLevel.BREAKING
                    if required
                    else CompatibilityLevel.ADDITIVE_COMPATIBLE,
                    path,
                    "required field added" if required else "optional field added",
                )
            )
        elif after is None:
            changes.append(
                SchemaChange(
                    SchemaChangeCode.FIELD_REMOVED,
                    CompatibilityLevel.BREAKING,
                    path,
                    "field removed",
                )
            )
        elif before is not None:
            changes.extend(_compare_definition(path, before, after))
    return tuple(changes)


def _flatten(
    field: FieldDefinition, parent: FieldPath | None = None
) -> tuple[tuple[FieldPath, FieldDefinition], ...]:
    path = FieldPath((field.key,)) if parent is None else parent.child(field.key)
    result = [(path, field)]
    value = field.value
    children = value.object_fields or value.table_columns
    if value.array_item is not None:
        children = value.array_item.object_fields
    for child in children:
        result.extend(_flatten(child, path))
    return tuple(result)


def _compare_definition(
    path: FieldPath, before: FieldDefinition, after: FieldDefinition
) -> tuple[SchemaChange, ...]:
    changes: list[SchemaChange] = []
    if before.value.field_type.kind != after.value.field_type.kind:
        return (
            SchemaChange(
                SchemaChangeCode.TYPE_CHANGED,
                CompatibilityLevel.BREAKING,
                path,
                "field type changed",
            ),
        )
    if before.cardinality != after.cardinality:
        tightened = (
            after.cardinality.minimum > before.cardinality.minimum
            or (before.cardinality.maximum is None and after.cardinality.maximum is not None)
            or (
                before.cardinality.maximum is not None
                and after.cardinality.maximum is not None
                and after.cardinality.maximum < before.cardinality.maximum
            )
        )
        changes.append(
            SchemaChange(
                SchemaChangeCode.CARDINALITY_TIGHTENED
                if tightened
                else SchemaChangeCode.CARDINALITY_RELAXED,
                CompatibilityLevel.BREAKING if tightened else CompatibilityLevel.BEHAVIOR_CHANGING,
                path,
                "field cardinality tightened" if tightened else "field cardinality relaxed",
            )
        )
    if before.value.field_type != after.value.field_type:
        changes.append(
            SchemaChange(
                SchemaChangeCode.CONSTRAINT_CHANGED,
                CompatibilityLevel.BEHAVIOR_CHANGING,
                path,
                "field type constraints changed",
            )
        )
    if before.artifacts != after.artifacts or before.value.artifacts != after.value.artifacts:
        changes.append(
            SchemaChange(
                SchemaChangeCode.ARTIFACT_BINDING_CHANGED,
                CompatibilityLevel.BEHAVIOR_CHANGING,
                path,
                "field artifact bindings changed",
            )
        )
    return tuple(changes)


def _level_rank(level: CompatibilityLevel) -> int:
    return {
        CompatibilityLevel.ADDITIVE_COMPATIBLE: 0,
        CompatibilityLevel.BEHAVIOR_CHANGING: 1,
        CompatibilityLevel.BREAKING: 2,
    }[level]


def _change_sort_key(change: SchemaChange) -> tuple[str, str]:
    return ("" if change.path is None else str(change.path), change.code.value)
