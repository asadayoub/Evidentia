"""Tests for immutable recursive schema definitions and published snapshots."""

from dataclasses import FrozenInstanceError

import pytest

from evidentia.modules.schemas.public import (
    ArrayType,
    ArtifactBindings,
    Cardinality,
    DecimalType,
    FieldDefinition,
    FieldKey,
    ObjectType,
    PublishedArtifactReference,
    PublishedSchemaModule,
    PublishedSchemaVersion,
    SchemaArtifactKind,
    SchemaId,
    SchemaLifecycleState,
    SchemaModuleId,
    SchemaVersion,
    StringType,
    TableType,
    ValueDefinition,
)

_DIGEST = "a" * 64


def _field(
    key: str,
    value: ValueDefinition | None = None,
    *,
    cardinality: Cardinality | None = None,
) -> FieldDefinition:
    return FieldDefinition(
        FieldKey(key),
        value or ValueDefinition.scalar(StringType()),
        cardinality or Cardinality(),
    )


def _module(*fields: FieldDefinition) -> PublishedSchemaModule:
    return PublishedSchemaModule(
        module_id=SchemaModuleId("550e8400-e29b-41d4-a716-446655440000"),
        version=SchemaVersion(1),
        key=FieldKey("invoice_core"),
        fields=tuple(fields),
    )


def test_cardinality_models_required_optional_and_repeated_fields() -> None:
    assert Cardinality().required is False
    assert Cardinality(1, 1).required is True
    assert Cardinality(0, None).maximum is None

    with pytest.raises(ValueError, match="non-negative"):
        Cardinality(-1, 1)
    with pytest.raises(ValueError, match="at least the minimum"):
        Cardinality(2, 1)
    with pytest.raises(ValueError, match="non-negative"):
        Cardinality(True, 1)


def test_recursive_objects_arrays_and_tables_produce_stable_paths() -> None:
    address = ValueDefinition.object(
        (
            _field("street"),
            _field("postal_code", cardinality=Cardinality(1, 1)),
        )
    )
    contacts = ValueDefinition.array(
        ValueDefinition.object((_field("name"), _field("email"))),
        field_type=ArrayType(min_items=1),
    )
    lines = ValueDefinition.table(
        (
            _field("description", cardinality=Cardinality(1, 1)),
            _field(
                "amount",
                ValueDefinition.scalar(DecimalType(precision=12, scale=2)),
                cardinality=Cardinality(1, 1),
            ),
        ),
        field_type=TableType(min_rows=1),
    )

    roots = (
        _field("supplier_address", address),
        _field("contacts", contacts),
        _field("line_items", lines),
    )
    module = _module(*roots)

    assert tuple(str(path) for path in roots[0].iter_paths()) == (
        "supplier_address",
        "supplier_address.street",
        "supplier_address.postal_code",
    )
    assert tuple(str(path) for path in roots[1].iter_paths()) == (
        "contacts",
        "contacts.name",
        "contacts.email",
    )
    assert tuple(str(path) for path in roots[2].iter_paths()) == (
        "line_items",
        "line_items.description",
        "line_items.amount",
    )
    assert module.fields == roots


def test_value_definitions_reject_invalid_container_shapes_and_nesting() -> None:
    with pytest.raises(ValueError, match="non-container"):
        ValueDefinition(field_type=StringType(), object_fields=(_field("child"),))
    with pytest.raises(ValueError, match="object values require"):
        ValueDefinition(field_type=ObjectType())
    with pytest.raises(ValueError, match="array values require"):
        ValueDefinition(field_type=ArrayType())
    with pytest.raises(ValueError, match="table values require"):
        ValueDefinition(field_type=TableType())
    with pytest.raises(ValueError, match="cannot be table"):
        ValueDefinition.array(ValueDefinition.table((_field("value"),)))
    with pytest.raises(ValueError, match="nested table"):
        ValueDefinition.table((_field("nested", ValueDefinition.table((_field("value"),))),))
    with pytest.raises(ValueError, match="maximum cardinality of one"):
        ValueDefinition.table((_field("repeated", cardinality=Cardinality(0, None)),))


def test_duplicate_field_paths_are_rejected_at_every_named_scope() -> None:
    with pytest.raises(ValueError, match="duplicate field keys"):
        ValueDefinition.object((_field("name"), _field("name")))
    with pytest.raises(ValueError, match="duplicate field keys"):
        ValueDefinition.table((_field("amount"), _field("amount")))
    with pytest.raises(ValueError, match="duplicate field keys"):
        _module(_field("invoice_number"), _field("invoice_number"))


def test_artifact_bindings_require_immutable_versioned_integrity_references() -> None:
    validation = PublishedArtifactReference(
        artifact_id="550E8400-E29B-41D4-A716-446655440000",
        version=SchemaVersion(3),
        kind=SchemaArtifactKind.VALIDATION_RULES,
        content_sha256=_DIGEST,
    )
    localization = PublishedArtifactReference(
        artifact_id="e29b41d4-a716-4466-9544-006655440000",
        version=SchemaVersion(2),
        kind=SchemaArtifactKind.LOCALIZATION,
        content_sha256="b" * 64,
    )
    bindings = ArtifactBindings((validation, localization))

    assert validation.artifact_id == "550e8400-e29b-41d4-a716-446655440000"
    assert bindings.for_kind(SchemaArtifactKind.VALIDATION_RULES) == (validation,)
    assert bindings.for_kind(SchemaArtifactKind.EXTRACTION_HINTS) == ()

    with pytest.raises(ValueError, match="lowercase SHA-256"):
        PublishedArtifactReference(
            validation.artifact_id,
            SchemaVersion(1),
            SchemaArtifactKind.VALIDATION_RULES,
            "A" * 64,
        )
    with pytest.raises(ValueError, match="duplicate version"):
        ArtifactBindings((validation, validation))
    with pytest.raises(ValueError, match="immutable tuple"):
        ArtifactBindings([validation])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="only published"):
        ArtifactBindings((None,))  # type: ignore[arg-type]


def test_published_modules_are_frozen_and_cannot_embed_draft_content() -> None:
    module = _module(_field("invoice_number"))

    assert module.reference.module_id == module.module_id
    assert module.reference.version == SchemaVersion(1)
    with pytest.raises(FrozenInstanceError):
        module.fields = ()  # type: ignore[misc]
    with pytest.raises(ValueError, match="mutable draft"):
        PublishedSchemaModule(
            module_id=SchemaModuleId.new(),
            version=SchemaVersion(1),
            key=FieldKey("draft_module"),
            fields=(_field("value"),),
            lifecycle=SchemaLifecycleState.DRAFT,
        )
    with pytest.raises(ValueError, match="immutable tuple"):
        PublishedSchemaModule(
            module_id=SchemaModuleId.new(),
            version=SchemaVersion(1),
            key=FieldKey("unsafe_module"),
            fields=[_field("value")],  # type: ignore[arg-type]
        )


def test_schema_snapshot_retains_exact_immutable_module_versions() -> None:
    module = _module(_field("invoice_number"))
    schema = PublishedSchemaVersion(
        schema_id=SchemaId("123e4567-e89b-12d3-a456-426614174000"),
        version=SchemaVersion(4),
        fields=(_field("received_at"),),
        modules=(module,),
    )

    assert schema.module_references == (module.reference,)
    assert schema.lifecycle is SchemaLifecycleState.PUBLISHED
    with pytest.raises(ValueError, match="repeat a module"):
        PublishedSchemaVersion(
            schema_id=schema.schema_id,
            version=SchemaVersion(5),
            modules=(module, module),
        )
    with pytest.raises(ValueError, match="fields, modules, or both"):
        PublishedSchemaVersion(schema_id=schema.schema_id, version=SchemaVersion(5))
    with pytest.raises(ValueError, match="mutable draft"):
        PublishedSchemaVersion(
            schema_id=schema.schema_id,
            version=SchemaVersion(5),
            modules=(module,),
            lifecycle=SchemaLifecycleState.DRAFT,
        )
