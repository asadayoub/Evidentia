"""Canonical, versioned JSON interchange for published schemas."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from evidentia.modules.schemas.domain.artifact_links import (
    ArtifactBindings,
    PublishedArtifactReference,
    SchemaArtifactKind,
)
from evidentia.modules.schemas.domain.definitions import (
    Cardinality,
    FieldDefinition,
    FieldType,
    ValueDefinition,
)
from evidentia.modules.schemas.domain.field_types import (
    ArrayType,
    ArtifactReferenceType,
    BooleanType,
    DateTimeType,
    DateType,
    DecimalType,
    EnumType,
    ExtensionType,
    IdentifierType,
    IntegerType,
    MoneyType,
    ObjectType,
    ReferenceType,
    StringType,
    TableType,
)
from evidentia.modules.schemas.domain.identity import (
    FieldKey,
    ReleaseLabel,
    SchemaId,
    SchemaModuleId,
    SchemaVersion,
)
from evidentia.modules.schemas.domain.modules import PublishedSchemaModule, PublishedSchemaVersion

INTERCHANGE_FORMAT = "evidentia.schema"
INTERCHANGE_VERSION = 1


@dataclass(frozen=True, slots=True)
class SchemaInterchangeEnvelope:
    """Versioned canonical schema interchange envelope.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    format: str
    version: int
    schema: PublishedSchemaVersion


def export_schema(schema: PublishedSchemaVersion) -> bytes:
    """Return deterministic UTF-8 JSON for one immutable schema snapshot.

    @skyhook-implements REQ-003
    @skyhook-implements CON-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """
    document = {
        "format": INTERCHANGE_FORMAT,
        "version": INTERCHANGE_VERSION,
        "schema": _schema_out(schema),
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def import_schema(payload: bytes | str) -> SchemaInterchangeEnvelope:
    """Validate and import a supported canonical schema envelope.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """
    try:
        document = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("schema interchange must be valid UTF-8 JSON") from error
    if not isinstance(document, dict) or document.get("format") != INTERCHANGE_FORMAT:
        raise ValueError("unsupported schema interchange format")
    if document.get("version") != INTERCHANGE_VERSION:
        raise ValueError("unsupported schema interchange version")
    return SchemaInterchangeEnvelope(
        INTERCHANGE_FORMAT, INTERCHANGE_VERSION, _schema_in(document.get("schema"))
    )


def _schema_out(schema: PublishedSchemaVersion) -> dict[str, Any]:
    return {
        "id": schema.schema_id.value,
        "version": schema.version.value,
        "releaseLabel": None if schema.release_label is None else schema.release_label.value,
        "fields": [_field_out(item) for item in schema.fields],
        "modules": [_module_out(item) for item in schema.modules],
        "artifacts": _artifacts_out(schema.artifacts),
    }


def _module_out(module: PublishedSchemaModule) -> dict[str, Any]:
    return {
        "id": module.module_id.value,
        "version": module.version.value,
        "key": module.key.value,
        "releaseLabel": None if module.release_label is None else module.release_label.value,
        "fields": [_field_out(item) for item in module.fields],
        "artifacts": _artifacts_out(module.artifacts),
    }


def _field_out(definition: FieldDefinition) -> dict[str, Any]:
    return {
        "key": definition.key.value,
        "cardinality": {
            "minimum": definition.cardinality.minimum,
            "maximum": definition.cardinality.maximum,
        },
        "artifacts": _artifacts_out(definition.artifacts),
        "value": _value_out(definition.value),
    }


def _value_out(value: ValueDefinition) -> dict[str, Any]:
    result = {"type": _type_out(value.field_type), "artifacts": _artifacts_out(value.artifacts)}
    if value.object_fields:
        result["objectFields"] = [_field_out(item) for item in value.object_fields]
    if value.array_item is not None:
        result["arrayItem"] = _value_out(value.array_item)
    if value.table_columns:
        result["tableColumns"] = [_field_out(item) for item in value.table_columns]
    return result


def _type_out(field_type: object) -> dict[str, Any]:
    kind = field_type.kind.value  # type: ignore[attr-defined]
    values = {"kind": kind}
    for name in getattr(field_type, "__dataclass_fields__", {}):
        if name == "kind":
            continue
        value = getattr(field_type, name)
        if isinstance(value, Decimal):
            value = format(value, "f")
        elif isinstance(value, tuple):
            value = list(value)
        elif isinstance(value, (DecimalType, IdentifierType)):
            value = _type_out(value)
        values[name] = value
    return values


def _artifacts_out(bindings: ArtifactBindings) -> list[dict[str, Any]]:
    return [
        {
            "id": item.artifact_id,
            "version": item.version.value,
            "kind": item.kind.value,
            "sha256": item.content_sha256,
        }
        for item in bindings.references
    ]


def _schema_in(raw: object) -> PublishedSchemaVersion:
    data = _object(raw, "schema")
    return PublishedSchemaVersion(
        schema_id=SchemaId(_string(data, "id")),
        version=SchemaVersion(_integer(data, "version")),
        fields=tuple(_field_in(item) for item in _list(data, "fields")),
        modules=tuple(_module_in(item) for item in _list(data, "modules")),
        release_label=_label(data.get("releaseLabel")),
        artifacts=_artifacts_in(data.get("artifacts", [])),
    )


def _module_in(raw: object) -> PublishedSchemaModule:
    data = _object(raw, "module")
    return PublishedSchemaModule(
        module_id=SchemaModuleId(_string(data, "id")),
        version=SchemaVersion(_integer(data, "version")),
        key=FieldKey(_string(data, "key")),
        fields=tuple(_field_in(item) for item in _list(data, "fields")),
        release_label=_label(data.get("releaseLabel")),
        artifacts=_artifacts_in(data.get("artifacts", [])),
    )


def _field_in(raw: object) -> FieldDefinition:
    data = _object(raw, "field")
    card = _object(data.get("cardinality"), "cardinality")
    maximum = card.get("maximum")
    if maximum is not None and (isinstance(maximum, bool) or not isinstance(maximum, int)):
        raise ValueError("cardinality maximum must be an integer or null")
    return FieldDefinition(
        FieldKey(_string(data, "key")),
        _value_in(data.get("value")),
        Cardinality(_integer(card, "minimum"), maximum),
        _artifacts_in(data.get("artifacts", [])),
    )


def _value_in(raw: object) -> ValueDefinition:
    data = _object(raw, "value")
    return ValueDefinition(
        field_type=_type_in(data.get("type")),
        object_fields=tuple(_field_in(item) for item in data.get("objectFields", [])),
        array_item=None if "arrayItem" not in data else _value_in(data["arrayItem"]),
        table_columns=tuple(_field_in(item) for item in data.get("tableColumns", [])),
        artifacts=_artifacts_in(data.get("artifacts", [])),
    )


def _type_in(raw: object) -> FieldType:
    data = _object(raw, "field type")
    kind = data.get("kind")
    constructors: dict[str, Callable[[], FieldType]] = {
        "string": lambda: StringType(
            data.get("min_length", 0), data.get("max_length"), data.get("pattern")
        ),
        "boolean": BooleanType,
        "integer": lambda: IntegerType(data.get("minimum"), data.get("maximum")),
        "decimal": lambda: DecimalType(
            data.get("precision"),
            data.get("scale"),
            _decimal(data.get("minimum")),
            _decimal(data.get("maximum")),
        ),
        "money": lambda: _money_type(data),
        "date": DateType,
        "datetime": DateTimeType,
        "enum": lambda: EnumType(tuple(data.get("values", []))),
        "identifier": lambda: IdentifierType(
            data.get("min_length", 1), data.get("max_length", 255), data.get("pattern")
        ),
        "reference": lambda: _reference_type(data),
        "object": lambda: ObjectType(data.get("min_properties", 0), data.get("max_properties")),
        "array": lambda: ArrayType(
            data.get("min_items", 0), data.get("max_items"), data.get("unique_items", False)
        ),
        "table": lambda: TableType(data.get("min_rows", 0), data.get("max_rows")),
        "artifact_reference": ArtifactReferenceType,
        "extension": lambda: ExtensionType(
            _string(data, "namespace"), _string(data, "name"), _integer(data, "version")
        ),
    }
    constructor = constructors.get(kind) if isinstance(kind, str) else None
    if constructor is None:
        raise ValueError(f"unknown core field type: {kind!r}")
    return constructor()


def _money_type(data: dict[str, Any]) -> MoneyType:
    amount = _type_in(data.get("amount"))
    if not isinstance(amount, DecimalType):
        raise ValueError("money amount must be a decimal type")
    return MoneyType(amount, tuple(data.get("allowed_currencies", [])))


def _reference_type(data: dict[str, Any]) -> ReferenceType:
    identifier = _type_in(data.get("identifier"))
    if not isinstance(identifier, IdentifierType):
        raise ValueError("reference identifier must be an identifier type")
    return ReferenceType(_string(data, "target"), identifier)


def _artifacts_in(raw: object) -> ArtifactBindings:
    if not isinstance(raw, list):
        raise ValueError("artifact bindings must be a list")
    return ArtifactBindings(
        tuple(
            PublishedArtifactReference(
                _string(item, "id"),
                SchemaVersion(_integer(item, "version")),
                SchemaArtifactKind(_string(item, "kind")),
                _string(item, "sha256"),
            )
            for item in raw
        )
    )


def _object(raw: object, subject: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise ValueError(f"{subject} must be an object")
    return raw


def _list(data: dict[str, Any], key: str) -> list[object]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _string(data: object, key: str) -> str:
    value = _object(data, "object").get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _integer(data: object, key: str) -> int:
    value = _object(data, "object").get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _label(value: object) -> ReleaseLabel | None:
    return None if value is None else ReleaseLabel(str(value))
