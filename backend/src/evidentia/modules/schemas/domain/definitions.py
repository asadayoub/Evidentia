"""Immutable recursive field definitions for document-neutral schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from evidentia.modules.schemas.domain.artifact_links import ArtifactBindings
from evidentia.modules.schemas.domain.field_types import (
    ArrayType,
    ArtifactReferenceType,
    BooleanType,
    DateTimeType,
    DateType,
    DecimalType,
    EnumType,
    ExtensionType,
    FieldTypeKind,
    IdentifierType,
    IntegerType,
    MoneyType,
    ObjectType,
    ReferenceType,
    StringType,
    TableType,
)
from evidentia.modules.schemas.domain.identity import FieldKey, FieldPath


class FieldType(Protocol):
    """Structural interface implemented by every governed field type.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    @property
    def kind(self) -> FieldTypeKind:
        """Return the stable serialized discriminator for the field type."""
        ...


_FIELD_TYPE_CLASSES = (
    StringType,
    BooleanType,
    IntegerType,
    DecimalType,
    MoneyType,
    DateType,
    DateTimeType,
    EnumType,
    IdentifierType,
    ReferenceType,
    ObjectType,
    ArrayType,
    TableType,
    ArtifactReferenceType,
    ExtensionType,
)


@dataclass(frozen=True, slots=True)
class Cardinality:
    """Allowed number of occurrences for a named field.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    minimum: int = 0
    maximum: int | None = 1

    def __post_init__(self) -> None:
        if isinstance(self.minimum, bool) or not isinstance(self.minimum, int) or self.minimum < 0:
            raise ValueError("cardinality minimum must be a non-negative integer")
        if self.maximum is not None and (
            isinstance(self.maximum, bool)
            or not isinstance(self.maximum, int)
            or self.maximum < self.minimum
        ):
            raise ValueError("cardinality maximum must be null or at least the minimum")

    @property
    def required(self) -> bool:
        """Return whether at least one occurrence is required."""
        return self.minimum > 0


@dataclass(frozen=True, slots=True)
class ValueDefinition:
    """A field's type plus the one legal recursive structure for that type.

    Object values own named child fields, arrays own one anonymous item value,
    and tables own named columns. Scalar and extension types cannot carry nested
    definitions.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    field_type: FieldType
    object_fields: tuple[FieldDefinition, ...] = ()
    array_item: ValueDefinition | None = None
    table_columns: tuple[FieldDefinition, ...] = ()
    artifacts: ArtifactBindings = field(default_factory=ArtifactBindings)

    def __post_init__(self) -> None:
        if not isinstance(self.field_type, _FIELD_TYPE_CLASSES):
            raise ValueError("value definition must use a governed field type")
        if not isinstance(self.object_fields, tuple) or not isinstance(self.table_columns, tuple):
            raise ValueError("nested named definitions must be retained in immutable tuples")
        if not isinstance(self.artifacts, ArtifactBindings):
            raise ValueError("value definition artifacts must use ArtifactBindings")

        kind = self.field_type.kind
        if kind is FieldTypeKind.OBJECT:
            if not self.object_fields or self.array_item is not None or self.table_columns:
                raise ValueError("object values require only one or more named object fields")
            _ensure_unique_sibling_keys(self.object_fields, "object")
            return
        if kind is FieldTypeKind.ARRAY:
            if (
                not isinstance(self.array_item, ValueDefinition)
                or self.object_fields
                or self.table_columns
            ):
                raise ValueError("array values require only one item definition")
            if self.array_item.field_type.kind is FieldTypeKind.TABLE:
                raise ValueError("array items cannot be table values")
            return
        if kind is FieldTypeKind.TABLE:
            if not self.table_columns or self.object_fields or self.array_item is not None:
                raise ValueError("table values require only one or more named columns")
            _ensure_unique_sibling_keys(self.table_columns, "table")
            for column in self.table_columns:
                if column.cardinality.maximum != 1:
                    raise ValueError("table columns must have a maximum cardinality of one")
                if column.value.field_type.kind is FieldTypeKind.TABLE:
                    raise ValueError("tables cannot contain nested table columns")
            return
        if self.object_fields or self.array_item is not None or self.table_columns:
            raise ValueError("non-container values cannot contain nested definitions")

    @classmethod
    def scalar(
        cls, field_type: FieldType, *, artifacts: ArtifactBindings | None = None
    ) -> ValueDefinition:
        """Construct a non-container value definition."""
        return cls(field_type=field_type, artifacts=artifacts or ArtifactBindings())

    @classmethod
    def object(
        cls,
        fields: tuple[FieldDefinition, ...],
        *,
        field_type: ObjectType | None = None,
        artifacts: ArtifactBindings | None = None,
    ) -> ValueDefinition:
        """Construct an object value with validated named children."""
        return cls(
            field_type=field_type or ObjectType(),
            object_fields=fields,
            artifacts=artifacts or ArtifactBindings(),
        )

    @classmethod
    def array(
        cls,
        item: ValueDefinition,
        *,
        field_type: ArrayType | None = None,
        artifacts: ArtifactBindings | None = None,
    ) -> ValueDefinition:
        """Construct an array value with one validated item definition."""
        return cls(
            field_type=field_type or ArrayType(),
            array_item=item,
            artifacts=artifacts or ArtifactBindings(),
        )

    @classmethod
    def table(
        cls,
        columns: tuple[FieldDefinition, ...],
        *,
        field_type: TableType | None = None,
        artifacts: ArtifactBindings | None = None,
    ) -> ValueDefinition:
        """Construct a line-item table with validated named columns."""
        return cls(
            field_type=field_type or TableType(),
            table_columns=columns,
            artifacts=artifacts or ArtifactBindings(),
        )


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    """Stable named field with cardinality and an immutable value definition.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    key: FieldKey
    value: ValueDefinition
    cardinality: Cardinality = field(default_factory=Cardinality)
    artifacts: ArtifactBindings = field(default_factory=ArtifactBindings)

    def __post_init__(self) -> None:
        if not isinstance(self.key, FieldKey):
            raise ValueError("field definition key must use FieldKey")
        if not isinstance(self.value, ValueDefinition):
            raise ValueError("field definition value must use ValueDefinition")
        if not isinstance(self.cardinality, Cardinality):
            raise ValueError("field definition cardinality must use Cardinality")
        if not isinstance(self.artifacts, ArtifactBindings):
            raise ValueError("field definition artifacts must use ArtifactBindings")

    def iter_paths(self, parent: FieldPath | None = None) -> tuple[FieldPath, ...]:
        """Return this field and all named descendants in deterministic order."""
        current = FieldPath((self.key,)) if parent is None else parent.child(self.key)
        paths = [current]
        paths.extend(_nested_paths(self.value, current))
        return tuple(paths)


def _ensure_unique_sibling_keys(fields: tuple[FieldDefinition, ...], subject: str) -> None:
    if not all(isinstance(item, FieldDefinition) for item in fields):
        raise ValueError(f"{subject} members must be FieldDefinition values")
    keys = [item.key for item in fields]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{subject} members must not contain duplicate field keys")


def _nested_paths(value: ValueDefinition, parent: FieldPath) -> tuple[FieldPath, ...]:
    if value.field_type.kind is FieldTypeKind.OBJECT:
        children = value.object_fields
    elif value.field_type.kind is FieldTypeKind.TABLE:
        children = value.table_columns
    elif value.field_type.kind is FieldTypeKind.ARRAY and value.array_item is not None:
        return _nested_paths(value.array_item, parent)
    else:
        children = ()

    paths: list[FieldPath] = []
    for child in children:
        paths.extend(child.iter_paths(parent))
    return tuple(paths)


def ensure_unique_root_fields(fields: tuple[FieldDefinition, ...]) -> None:
    """Reject duplicate roots and verify every recursively produced path is unique.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """
    _ensure_unique_sibling_keys(fields, "schema root")
    paths = [path for definition in fields for path in definition.iter_paths()]
    if len(set(paths)) != len(paths):
        raise ValueError("schema definition must not contain duplicate field paths")
