"""Deterministic composition of immutable published schema modules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import Any

from evidentia.modules.schemas.domain.definitions import FieldDefinition, ValueDefinition
from evidentia.modules.schemas.domain.field_types import FieldTypeKind
from evidentia.modules.schemas.domain.identity import FieldKey, FieldPath, SchemaId, SchemaVersion
from evidentia.modules.schemas.domain.modules import (
    PublishedSchemaModule,
    PublishedSchemaVersion,
    SchemaModuleReference,
)


@dataclass(frozen=True, slots=True)
class FieldSelector:
    """Select one field from schema-local content or an exact module version.

    A null module selects schema-local fields. Module selectors always retain the
    exact module identity and version used by the published schema snapshot.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    path: FieldPath
    module: SchemaModuleReference | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, FieldPath):
            raise ValueError("field selector path must use FieldPath")
        if self.module is not None and not isinstance(self.module, SchemaModuleReference):
            raise ValueError("field selector module must use SchemaModuleReference")


@dataclass(frozen=True, slots=True)
class FieldAlias:
    """Export a selected field under another key within the same parent.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    source: FieldSelector
    alias: FieldKey

    def __post_init__(self) -> None:
        if not isinstance(self.source, FieldSelector) or not isinstance(self.alias, FieldKey):
            raise ValueError("field alias requires a selector and a stable alias key")
        if self.alias == self.source.path.segments[-1]:
            raise ValueError("field alias must differ from the selected field key")

    @property
    def target_path(self) -> FieldPath:
        """Return the source parent plus the governed alias key."""
        return FieldPath((*self.source.path.segments[:-1], self.alias))


@dataclass(frozen=True, slots=True)
class FieldMapping:
    """Declare two same-parent fields equivalent under the target field path.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    source: FieldSelector
    target: FieldSelector

    def __post_init__(self) -> None:
        _validate_pair(self.source, self.target, "mapping")
        if self.source == self.target:
            raise ValueError("mapping source and target must be different fields")


@dataclass(frozen=True, slots=True)
class FieldReplacement:
    """Explicitly replace one selected target with another same-parent field.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    replacement: FieldSelector
    target: FieldSelector

    def __post_init__(self) -> None:
        _validate_pair(self.replacement, self.target, "replacement")
        if self.replacement == self.target:
            raise ValueError("replacement source and target must be different fields")


type CompositionDirective = FieldAlias | FieldMapping | FieldReplacement


class CompositionConflictCode(StrEnum):
    """Stable machine code for an explainable composition failure.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    INVALID_DIRECTIVE = "invalid_directive"
    MISSING_FIELD = "missing_field"
    DUPLICATE_FIELD = "duplicate_field"
    INCOMPATIBLE_TYPE = "incompatible_type"
    INCOMPATIBLE_DEFINITION = "incompatible_definition"


@dataclass(frozen=True, slots=True)
class FieldOrigin:
    """Source module and resolved path attached to a conflict diagnostic.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    path: FieldPath
    module: SchemaModuleReference | None = None

    @property
    def label(self) -> str:
        """Return a stable human-readable source label."""
        if self.module is None:
            return f"schema:{self.path}"
        return f"module:{self.module.module_id}@{self.module.version.value}:{self.path}"


@dataclass(frozen=True, slots=True)
class CompositionConflict:
    """Deterministically ordered, explainable schema composition conflict.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    code: CompositionConflictCode
    path: FieldPath
    message: str
    origins: tuple[FieldOrigin, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.origins, tuple):
            raise ValueError("composition conflict origins must use an immutable tuple")


@dataclass(frozen=True, slots=True)
class ResolvedSchemaIdentity:
    """SHA-256 identity of canonical composition inputs and resolved fields.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or len(self.value) != 64
            or any(character not in "0123456789abcdef" for character in self.value)
        ):
            raise ValueError("resolved schema identity must be lowercase SHA-256 hexadecimal")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ResolvedSchema:
    """Immutable successful result of deterministic schema composition.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    identity: ResolvedSchemaIdentity
    schema_id: SchemaId
    version: SchemaVersion
    fields: tuple[FieldDefinition, ...]
    modules: tuple[SchemaModuleReference, ...]
    directives: tuple[CompositionDirective, ...]

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, tuple) for value in (self.fields, self.modules, self.directives)
        ):
            raise ValueError("resolved schema collections must use immutable tuples")


@dataclass(frozen=True, slots=True)
class CompositionResult:
    """Either one resolved schema or a stable non-empty conflict collection.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    resolved: ResolvedSchema | None
    conflicts: tuple[CompositionConflict, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.conflicts, tuple):
            raise ValueError("composition result conflicts must use an immutable tuple")
        if (self.resolved is None) == (not self.conflicts):
            raise ValueError("composition result must contain either a schema or conflicts")


@dataclass(frozen=True, slots=True)
class _SourcedField:
    field: FieldDefinition
    module: SchemaModuleReference | None


def _validate_pair(source: FieldSelector, target: FieldSelector, subject: str) -> None:
    if not isinstance(source, FieldSelector) or not isinstance(target, FieldSelector):
        raise ValueError(f"field {subject} requires source and target selectors")
    if source.path.segments[:-1] != target.path.segments[:-1]:
        raise ValueError(f"field {subject} source and target must share the same parent path")


def _module_sort_key(module: PublishedSchemaModule) -> tuple[str, str, int]:
    return (module.key.value, module.module_id.value, module.version.value)


def _selector_sort_key(selector: FieldSelector) -> tuple[str, str, str]:
    module_id = selector.module.module_id.value if selector.module is not None else ""
    version = str(selector.module.version.value) if selector.module is not None else "0"
    return (str(selector.path), module_id, version)


def _directive_sort_key(directive: CompositionDirective) -> tuple[str, ...]:
    if isinstance(directive, FieldAlias):
        return ("alias", *_selector_sort_key(directive.source), str(directive.target_path))
    if isinstance(directive, FieldMapping):
        return (
            "mapping",
            *_selector_sort_key(directive.source),
            *_selector_sort_key(directive.target),
        )
    return (
        "replacement",
        *_selector_sort_key(directive.replacement),
        *_selector_sort_key(directive.target),
    )


def _find_field(fields_: tuple[FieldDefinition, ...], path: FieldPath) -> FieldDefinition | None:
    current_fields = fields_
    found: FieldDefinition | None = None
    for index, segment in enumerate(path.segments):
        found = next((item for item in current_fields if item.key == segment), None)
        if found is None:
            return None
        if index < len(path.segments) - 1:
            current_fields = _named_children(found.value)
            if not current_fields:
                return None
    return found


def _named_children(value: ValueDefinition) -> tuple[FieldDefinition, ...]:
    if value.field_type.kind is FieldTypeKind.OBJECT:
        return value.object_fields
    if value.field_type.kind is FieldTypeKind.TABLE:
        return value.table_columns
    if value.field_type.kind is FieldTypeKind.ARRAY and value.array_item is not None:
        return _named_children(value.array_item)
    return ()


def _replace_named_children(
    value: ValueDefinition, children: tuple[FieldDefinition, ...]
) -> ValueDefinition:
    if value.field_type.kind is FieldTypeKind.OBJECT:
        return replace(value, object_fields=children)
    if value.field_type.kind is FieldTypeKind.TABLE:
        return replace(value, table_columns=children)
    if value.field_type.kind is FieldTypeKind.ARRAY and value.array_item is not None:
        return replace(value, array_item=_replace_named_children(value.array_item, children))
    raise ValueError("selected field path does not have a named container parent")


def _remove_field(
    fields_: tuple[FieldDefinition, ...], path: FieldPath
) -> tuple[FieldDefinition, ...]:
    head, *tail = path.segments
    result: list[FieldDefinition] = []
    for item in fields_:
        if item.key != head:
            result.append(item)
            continue
        if not tail:
            continue
        child_path = FieldPath(tuple(tail))
        children = _remove_field(_named_children(item.value), child_path)
        result.append(replace(item, value=_replace_named_children(item.value, children)))
    return tuple(result)


def _rename_field(
    fields_: tuple[FieldDefinition, ...], path: FieldPath, key: FieldKey
) -> tuple[FieldDefinition, ...]:
    head, *tail = path.segments
    result: list[FieldDefinition] = []
    for item in fields_:
        if item.key != head:
            result.append(item)
            continue
        if not tail:
            result.append(replace(item, key=key))
            continue
        child_path = FieldPath(tuple(tail))
        children = _rename_field(_named_children(item.value), child_path, key)
        result.append(replace(item, value=_replace_named_children(item.value, children)))
    return tuple(result)


def _origin_sort_key(origin: FieldOrigin) -> str:
    return origin.label


def _conflict_sort_key(conflict: CompositionConflict) -> tuple[str, str, str, tuple[str, ...]]:
    return (
        str(conflict.path),
        conflict.code.value,
        conflict.message,
        tuple(origin.label for origin in conflict.origins),
    )


def _conflict(
    code: CompositionConflictCode,
    path: FieldPath,
    message: str,
    sourced: tuple[_SourcedField, ...] = (),
) -> CompositionConflict:
    origins = tuple(
        sorted(
            (FieldOrigin(path=path, module=item.module) for item in sourced),
            key=_origin_sort_key,
        )
    )
    return CompositionConflict(code=code, path=path, message=message, origins=origins)


def _same_field_except_key(left: FieldDefinition, right: FieldDefinition) -> bool:
    return replace(left, key=right.key) == right


def _mapping_authorizes(
    sourced: tuple[_SourcedField, ...],
    path: FieldPath,
    mappings: frozenset[
        tuple[SchemaModuleReference | None, SchemaModuleReference | None, FieldPath]
    ],
) -> bool:
    if len(sourced) != 2:
        return False
    modules = {item.module for item in sourced}
    return any(
        source in modules and target in modules and source != target
        for source, target, mapped_path in mappings
        if mapped_path == path
    )


def _merge_sourced_fields(
    sourced: tuple[_SourcedField, ...],
    parent: FieldPath | None,
    mappings: frozenset[
        tuple[SchemaModuleReference | None, SchemaModuleReference | None, FieldPath]
    ],
) -> tuple[tuple[FieldDefinition, ...], tuple[CompositionConflict, ...]]:
    grouped: dict[FieldKey, list[_SourcedField]] = {}
    for item in sourced:
        grouped.setdefault(item.field.key, []).append(item)

    merged: list[FieldDefinition] = []
    conflicts: list[CompositionConflict] = []
    for key in sorted(grouped, key=lambda item: item.value):
        group = tuple(grouped[key])
        path = FieldPath((key,)) if parent is None else parent.child(key)
        if len(group) == 1:
            merged.append(group[0].field)
            continue
        resolved, collision_conflicts = _merge_collision(group, path, mappings)
        if collision_conflicts:
            conflicts.extend(collision_conflicts)
        elif resolved is not None:
            merged.append(resolved)
    return tuple(merged), tuple(conflicts)


def _merge_collision(
    sourced: tuple[_SourcedField, ...],
    path: FieldPath,
    mappings: frozenset[
        tuple[SchemaModuleReference | None, SchemaModuleReference | None, FieldPath]
    ],
) -> tuple[FieldDefinition | None, tuple[CompositionConflict, ...]]:
    first = sourced[0].field
    kinds = {item.field.value.field_type.kind for item in sourced}
    if len(kinds) != 1:
        return None, (
            _conflict(
                CompositionConflictCode.INCOMPATIBLE_TYPE,
                path,
                "field path has incompatible type kinds",
                sourced,
            ),
        )
    if _mapping_authorizes(sourced, path, mappings):
        if _same_field_except_key(sourced[0].field, sourced[1].field):
            target_module = next(
                target
                for source, target, mapped_path in mappings
                if mapped_path == path
                and source in {item.module for item in sourced}
                and target in {item.module for item in sourced}
            )
            selected = next(item.field for item in sourced if item.module == target_module)
            return selected, ()
        return None, (
            _conflict(
                CompositionConflictCode.INCOMPATIBLE_DEFINITION,
                path,
                "explicitly mapped fields do not have equivalent definitions",
                sourced,
            ),
        )

    if any(
        item.field.cardinality != first.cardinality
        or item.field.artifacts != first.artifacts
        or item.field.value.field_type != first.value.field_type
        or item.field.value.artifacts != first.value.artifacts
        for item in sourced[1:]
    ):
        return None, (
            _conflict(
                CompositionConflictCode.INCOMPATIBLE_DEFINITION,
                path,
                "field path has incompatible constraints or artifact bindings",
                sourced,
            ),
        )

    kind = first.value.field_type.kind
    if kind is FieldTypeKind.OBJECT:
        return _merge_container(sourced, path, mappings, "object_fields")
    if kind is FieldTypeKind.TABLE:
        return _merge_container(sourced, path, mappings, "table_columns")
    if kind is FieldTypeKind.ARRAY:
        items = tuple(item.field.value.array_item for item in sourced)
        if all(item is not None for item in items):
            item_values = tuple(item for item in items if item is not None)
            merged_item, nested_conflicts = _merge_array_items(
                item_values, tuple(item.module for item in sourced), path, mappings
            )
            if nested_conflicts:
                return None, nested_conflicts
            if merged_item is not None:
                return replace(first, value=replace(first.value, array_item=merged_item)), ()

    return None, (
        _conflict(
            CompositionConflictCode.DUPLICATE_FIELD,
            path,
            "field path is declared more than once without an explicit mapping or replacement",
            sourced,
        ),
    )


def _merge_container(
    sourced: tuple[_SourcedField, ...],
    path: FieldPath,
    mappings: frozenset[
        tuple[SchemaModuleReference | None, SchemaModuleReference | None, FieldPath]
    ],
    attribute: str,
) -> tuple[FieldDefinition | None, tuple[CompositionConflict, ...]]:
    nested = tuple(
        _SourcedField(field=child, module=item.module)
        for item in sourced
        for child in getattr(item.field.value, attribute)
    )
    merged_children, conflicts = _merge_sourced_fields(nested, path, mappings)
    if conflicts:
        return None, conflicts
    first = sourced[0].field
    if attribute == "object_fields":
        value = replace(first.value, object_fields=merged_children)
    else:
        value = replace(first.value, table_columns=merged_children)
    return replace(first, value=value), ()


def _merge_array_items(
    values: tuple[ValueDefinition, ...],
    modules: tuple[SchemaModuleReference | None, ...],
    path: FieldPath,
    mappings: frozenset[
        tuple[SchemaModuleReference | None, SchemaModuleReference | None, FieldPath]
    ],
) -> tuple[ValueDefinition | None, tuple[CompositionConflict, ...]]:
    first = values[0]
    if any(
        value.field_type != first.field_type or value.artifacts != first.artifacts
        for value in values[1:]
    ):
        sourced = tuple(
            _SourcedField(FieldDefinition(path.segments[-1], value), module)
            for value, module in zip(values, modules, strict=True)
        )
        return None, (
            _conflict(
                CompositionConflictCode.INCOMPATIBLE_DEFINITION,
                path,
                "array item definitions are incompatible",
                sourced,
            ),
        )
    if first.field_type.kind is FieldTypeKind.OBJECT:
        attribute = "object_fields"
    elif first.field_type.kind is FieldTypeKind.TABLE:
        attribute = "table_columns"
    elif first.field_type.kind is FieldTypeKind.ARRAY:
        nested_values = tuple(value.array_item for value in values)
        if all(value is not None for value in nested_values):
            merged_nested, conflicts = _merge_array_items(
                tuple(value for value in nested_values if value is not None),
                modules,
                path,
                mappings,
            )
            if conflicts:
                return None, conflicts
            if merged_nested is not None:
                return replace(first, array_item=merged_nested), ()
        return None, ()
    else:
        return None, ()

    nested = tuple(
        _SourcedField(field=child, module=module)
        for value, module in zip(values, modules, strict=True)
        for child in getattr(value, attribute)
    )
    merged, conflicts = _merge_sourced_fields(nested, path, mappings)
    if conflicts:
        return None, conflicts
    if attribute == "object_fields":
        return replace(first, object_fields=merged), ()
    return replace(first, table_columns=merged), ()


def _canonical_value(value: object) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return format(value, "f")
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _canonical_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    return value


def _resolved_identity(
    schema: PublishedSchemaVersion,
    resolved_fields: tuple[FieldDefinition, ...],
    module_references: tuple[SchemaModuleReference, ...],
    directives: tuple[CompositionDirective, ...],
) -> ResolvedSchemaIdentity:
    payload = {
        "schema_id": schema.schema_id.value,
        "version": schema.version.value,
        "fields": _canonical_value(resolved_fields),
        "modules": _canonical_value(module_references),
        "directives": _canonical_value(directives),
        "artifacts": _canonical_value(schema.artifacts),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return ResolvedSchemaIdentity(hashlib.sha256(encoded.encode()).hexdigest())


def compose_schema(
    schema: PublishedSchemaVersion,
    directives: tuple[CompositionDirective, ...] = (),
) -> CompositionResult:
    """Compose one immutable schema snapshot with deterministic diagnostics.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """
    if not isinstance(schema, PublishedSchemaVersion):
        raise ValueError("composition requires a published schema snapshot")
    if not isinstance(directives, tuple) or not all(
        isinstance(item, (FieldAlias, FieldMapping, FieldReplacement)) for item in directives
    ):
        raise ValueError("composition directives must be an immutable tuple of governed directives")

    ordered_modules = tuple(sorted(schema.modules, key=_module_sort_key))
    groups: dict[SchemaModuleReference | None, tuple[FieldDefinition, ...]] = {
        None: schema.fields,
        **{module.reference: module.fields for module in ordered_modules},
    }
    ordered_directives = tuple(sorted(directives, key=_directive_sort_key))
    conflicts: list[CompositionConflict] = []
    seen_sources: set[FieldSelector] = set()
    removals: dict[SchemaModuleReference | None, list[FieldPath]] = {}
    renames: dict[SchemaModuleReference | None, list[tuple[FieldPath, FieldKey]]] = {}
    rename_targets: set[tuple[SchemaModuleReference | None, FieldPath]] = set()
    mappings: set[tuple[SchemaModuleReference | None, SchemaModuleReference | None, FieldPath]] = (
        set()
    )

    for directive in ordered_directives:
        source = (
            directive.source
            if not isinstance(directive, FieldReplacement)
            else directive.replacement
        )
        if source in seen_sources:
            conflicts.append(
                CompositionConflict(
                    CompositionConflictCode.INVALID_DIRECTIVE,
                    source.path,
                    "a selected source field has more than one composition directive",
                )
            )
            continue
        seen_sources.add(source)
        source_fields = groups.get(source.module)
        if source_fields is None or _find_field(source_fields, source.path) is None:
            conflicts.append(
                CompositionConflict(
                    CompositionConflictCode.MISSING_FIELD,
                    source.path,
                    "composition directive source does not exist in the selected snapshot",
                )
            )
            continue

        if isinstance(directive, FieldAlias):
            target_path = directive.target_path
            if _find_field(source_fields, target_path) is not None:
                conflicts.append(
                    CompositionConflict(
                        CompositionConflictCode.INVALID_DIRECTIVE,
                        target_path,
                        "field alias target already exists in the selected source",
                    )
                )
                continue
            if (source.module, target_path) in rename_targets:
                conflicts.append(
                    CompositionConflict(
                        CompositionConflictCode.INVALID_DIRECTIVE,
                        target_path,
                        "more than one directive produces the same field path in one source",
                    )
                )
                continue
            rename_targets.add((source.module, target_path))
            renames.setdefault(source.module, []).append((source.path, directive.alias))
            continue

        target = directive.target
        target_fields = groups.get(target.module)
        source_field = _find_field(source_fields, source.path)
        target_field = _find_field(target_fields or (), target.path)
        if target_fields is None or target_field is None:
            conflicts.append(
                CompositionConflict(
                    CompositionConflictCode.MISSING_FIELD,
                    target.path,
                    "composition directive target does not exist in the selected snapshot",
                )
            )
            continue
        if isinstance(directive, FieldMapping):
            if source.module == target.module:
                if source_field is None or not _same_field_except_key(source_field, target_field):
                    conflicts.append(
                        CompositionConflict(
                            CompositionConflictCode.INVALID_DIRECTIVE,
                            target.path,
                            "same-source mapping fields must have equivalent definitions",
                        )
                    )
                    continue
                removals.setdefault(source.module, []).append(source.path)
            else:
                if _find_field(source_fields, target.path) is not None:
                    conflicts.append(
                        CompositionConflict(
                            CompositionConflictCode.INVALID_DIRECTIVE,
                            target.path,
                            "field mapping target path already exists in the source module",
                        )
                    )
                    continue
                if (source.module, target.path) in rename_targets:
                    conflicts.append(
                        CompositionConflict(
                            CompositionConflictCode.INVALID_DIRECTIVE,
                            target.path,
                            "more than one directive produces the same field path in one source",
                        )
                    )
                    continue
                rename_targets.add((source.module, target.path))
                renames.setdefault(source.module, []).append(
                    (source.path, target.path.segments[-1])
                )
                mappings.add((source.module, target.module, target.path))
            continue

        if source.module != target.module and _find_field(source_fields, target.path) is not None:
            conflicts.append(
                CompositionConflict(
                    CompositionConflictCode.INVALID_DIRECTIVE,
                    target.path,
                    "field replacement target path already exists in the replacement module",
                )
            )
            continue
        if (source.module, target.path) in rename_targets:
            conflicts.append(
                CompositionConflict(
                    CompositionConflictCode.INVALID_DIRECTIVE,
                    target.path,
                    "more than one directive produces the same field path in one source",
                )
            )
            continue
        rename_targets.add((source.module, target.path))
        removals.setdefault(target.module, []).append(target.path)
        renames.setdefault(source.module, []).append((source.path, target.path.segments[-1]))

    if conflicts:
        return CompositionResult(None, tuple(sorted(conflicts, key=_conflict_sort_key)))

    transformed: dict[SchemaModuleReference | None, tuple[FieldDefinition, ...]] = {}
    for module, module_fields in groups.items():
        current = module_fields
        for path in sorted(
            removals.get(module, ()), key=lambda item: len(item.segments), reverse=True
        ):
            current = _remove_field(current, path)
        for path, key in sorted(
            renames.get(module, ()), key=lambda item: len(item[0].segments), reverse=True
        ):
            current = _rename_field(current, path, key)
        transformed[module] = current

    sourced = tuple(
        _SourcedField(field=item, module=module)
        for module in (None, *(item.reference for item in ordered_modules))
        for item in transformed[module]
    )
    resolved_fields, merge_conflicts = _merge_sourced_fields(sourced, None, frozenset(mappings))
    if merge_conflicts:
        return CompositionResult(None, tuple(sorted(merge_conflicts, key=_conflict_sort_key)))

    module_references = tuple(module.reference for module in ordered_modules)
    identity = _resolved_identity(schema, resolved_fields, module_references, ordered_directives)
    return CompositionResult(
        ResolvedSchema(
            identity=identity,
            schema_id=schema.schema_id,
            version=schema.version,
            fields=resolved_fields,
            modules=module_references,
            directives=ordered_directives,
        )
    )
