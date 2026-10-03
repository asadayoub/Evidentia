"""Tests for deterministic schema composition and conflict diagnostics."""

from evidentia.modules.schemas.public import (
    ArrayType,
    Cardinality,
    CompositionConflictCode,
    DecimalType,
    FieldAlias,
    FieldDefinition,
    FieldKey,
    FieldMapping,
    FieldPath,
    FieldReplacement,
    FieldSelector,
    PublishedSchemaModule,
    PublishedSchemaVersion,
    SchemaId,
    SchemaModuleId,
    SchemaVersion,
    StringType,
    TableType,
    ValueDefinition,
    resolve_schema,
)


def _field(
    key: str,
    value: ValueDefinition | None = None,
    *,
    required: bool = False,
) -> FieldDefinition:
    return FieldDefinition(
        FieldKey(key),
        value or ValueDefinition.scalar(StringType()),
        Cardinality(1, 1) if required else Cardinality(),
    )


def _module(identity: str, key: str, *fields: FieldDefinition) -> PublishedSchemaModule:
    return PublishedSchemaModule(
        module_id=SchemaModuleId(identity),
        version=SchemaVersion(1),
        key=FieldKey(key),
        fields=tuple(fields),
    )


def _schema(*modules: PublishedSchemaModule) -> PublishedSchemaVersion:
    return PublishedSchemaVersion(
        schema_id=SchemaId("123e4567-e89b-12d3-a456-426614174000"),
        version=SchemaVersion(2),
        modules=modules,
    )


def _selector(module: PublishedSchemaModule, path: str) -> FieldSelector:
    return FieldSelector(FieldPath.parse(path), module.reference)


def test_module_input_order_does_not_change_fields_modules_or_identity() -> None:
    supplier = _module(
        "00000000-0000-4000-8000-000000000002",
        "supplier",
        _field("supplier_name"),
    )
    invoice = _module(
        "00000000-0000-4000-8000-000000000001",
        "invoice",
        _field("invoice_number"),
    )

    first = resolve_schema(_schema(supplier, invoice)).resolved
    second = resolve_schema(_schema(invoice, supplier)).resolved

    assert first is not None
    assert second is not None
    assert first.fields == second.fields
    assert first.modules == second.modules
    assert first.identity == second.identity
    assert tuple(field.key.value for field in first.fields) == (
        "invoice_number",
        "supplier_name",
    )


def test_compatible_objects_and_tables_merge_recursively() -> None:
    core = _module(
        "00000000-0000-4000-8000-000000000001",
        "core",
        _field("supplier", ValueDefinition.object((_field("name"),))),
        _field(
            "line_items",
            ValueDefinition.table(
                (_field("description", required=True),),
                field_type=TableType(min_rows=1),
            ),
        ),
    )
    finance = _module(
        "00000000-0000-4000-8000-000000000002",
        "finance",
        _field("supplier", ValueDefinition.object((_field("tax_id"),))),
        _field(
            "line_items",
            ValueDefinition.table(
                (
                    _field(
                        "amount",
                        ValueDefinition.scalar(DecimalType(precision=12, scale=2)),
                        required=True,
                    ),
                ),
                field_type=TableType(min_rows=1),
            ),
        ),
    )

    result = resolve_schema(_schema(finance, core))

    assert result.conflicts == ()
    assert result.resolved is not None
    supplier = result.resolved.fields[1]
    table = result.resolved.fields[0]
    assert tuple(field.key.value for field in supplier.value.object_fields) == ("name", "tax_id")
    assert tuple(field.key.value for field in table.value.table_columns) == (
        "amount",
        "description",
    )


def test_nested_arrays_preserve_each_container_while_merging_object_items() -> None:
    first = _module(
        "00000000-0000-4000-8000-000000000001",
        "first",
        _field(
            "groups",
            ValueDefinition.array(
                ValueDefinition.array(
                    ValueDefinition.object((_field("name"),)),
                    field_type=ArrayType(min_items=1),
                )
            ),
        ),
    )
    second = _module(
        "00000000-0000-4000-8000-000000000002",
        "second",
        _field(
            "groups",
            ValueDefinition.array(
                ValueDefinition.array(
                    ValueDefinition.object((_field("code"),)),
                    field_type=ArrayType(min_items=1),
                )
            ),
        ),
    )

    resolved = resolve_schema(_schema(second, first)).resolved

    assert resolved is not None
    outer_item = resolved.fields[0].value.array_item
    assert outer_item is not None
    inner_item = outer_item.array_item
    assert inner_item is not None
    assert tuple(field.key.value for field in inner_item.object_fields) == ("code", "name")


def test_scalar_duplicates_and_incompatible_types_return_stable_conflicts() -> None:
    first = _module("00000000-0000-4000-8000-000000000001", "first", _field("invoice_number"))
    duplicate = _module("00000000-0000-4000-8000-000000000002", "second", _field("invoice_number"))
    incompatible = _module(
        "00000000-0000-4000-8000-000000000003",
        "third",
        _field("invoice_number", ValueDefinition.scalar(DecimalType(10, 0))),
    )

    duplicate_result = resolve_schema(_schema(duplicate, first))
    incompatible_result = resolve_schema(_schema(incompatible, first))

    assert duplicate_result.resolved is None
    assert duplicate_result.conflicts[0].code is CompositionConflictCode.DUPLICATE_FIELD
    assert str(duplicate_result.conflicts[0].path) == "invoice_number"
    assert tuple(origin.label for origin in duplicate_result.conflicts[0].origins) == tuple(
        sorted(origin.label for origin in duplicate_result.conflicts[0].origins)
    )
    assert incompatible_result.conflicts[0].code is CompositionConflictCode.INCOMPATIBLE_TYPE


def test_all_nested_conflicts_are_returned_in_stable_path_order() -> None:
    first = _module(
        "00000000-0000-4000-8000-000000000001",
        "first",
        _field("party", ValueDefinition.object((_field("name"), _field("tax_id")))),
    )
    second = _module(
        "00000000-0000-4000-8000-000000000002",
        "second",
        _field("party", ValueDefinition.object((_field("tax_id"), _field("name")))),
    )

    result = resolve_schema(_schema(second, first))

    assert result.resolved is None
    assert tuple(str(conflict.path) for conflict in result.conflicts) == (
        "party.name",
        "party.tax_id",
    )


def test_alias_renames_a_selected_nested_field_without_silent_override() -> None:
    module = _module(
        "00000000-0000-4000-8000-000000000001",
        "supplier",
        _field("supplier", ValueDefinition.object((_field("name"), _field("tax_id")))),
    )
    alias = FieldAlias(_selector(module, "supplier.tax_id"), FieldKey("vat_number"))

    resolved = resolve_schema(_schema(module), (alias,)).resolved

    assert resolved is not None
    assert tuple(field.key.value for field in resolved.fields[0].value.object_fields) == (
        "name",
        "vat_number",
    )


def test_alias_collision_returns_a_governed_diagnostic() -> None:
    module = _module(
        "00000000-0000-4000-8000-000000000001",
        "supplier",
        _field("supplier", ValueDefinition.object((_field("name"), _field("tax_id")))),
    )
    alias = FieldAlias(_selector(module, "supplier.tax_id"), FieldKey("name"))

    result = resolve_schema(_schema(module), (alias,))

    assert result.resolved is None
    assert result.conflicts[0].code is CompositionConflictCode.INVALID_DIRECTIVE
    assert str(result.conflicts[0].path) == "supplier.name"


def test_explicit_mapping_collapses_equivalent_cross_module_fields() -> None:
    legacy = _module("00000000-0000-4000-8000-000000000001", "legacy", _field("vendor_name"))
    canonical = _module(
        "00000000-0000-4000-8000-000000000002", "canonical", _field("supplier_name")
    )
    mapping = FieldMapping(
        source=_selector(legacy, "vendor_name"),
        target=_selector(canonical, "supplier_name"),
    )

    result = resolve_schema(_schema(canonical, legacy), (mapping,))

    assert result.conflicts == ()
    assert result.resolved is not None
    assert tuple(field.key.value for field in result.resolved.fields) == ("supplier_name",)


def test_mapping_rejects_non_equivalent_definitions() -> None:
    legacy = _module("00000000-0000-4000-8000-000000000001", "legacy", _field("vendor_name"))
    canonical = _module(
        "00000000-0000-4000-8000-000000000002",
        "canonical",
        _field("supplier_name", ValueDefinition.scalar(StringType(min_length=1))),
    )
    mapping = FieldMapping(_selector(legacy, "vendor_name"), _selector(canonical, "supplier_name"))

    result = resolve_schema(_schema(legacy, canonical), (mapping,))

    assert result.resolved is None
    assert result.conflicts[0].code is CompositionConflictCode.INCOMPATIBLE_DEFINITION


def test_explicit_replacement_uses_replacement_definition_at_target_path() -> None:
    core = _module("00000000-0000-4000-8000-000000000001", "core", _field("amount"))
    jurisdiction = _module(
        "00000000-0000-4000-8000-000000000002",
        "jurisdiction",
        _field("regulated_amount", ValueDefinition.scalar(DecimalType(12, 2))),
    )
    replacement = FieldReplacement(
        replacement=_selector(jurisdiction, "regulated_amount"),
        target=_selector(core, "amount"),
    )

    resolved = resolve_schema(_schema(core, jurisdiction), (replacement,)).resolved

    assert resolved is not None
    assert tuple(field.key.value for field in resolved.fields) == ("amount",)
    assert resolved.fields[0].value.field_type == DecimalType(12, 2)


def test_missing_and_repeated_directive_sources_return_explainable_conflicts() -> None:
    module = _module("00000000-0000-4000-8000-000000000001", "core", _field("invoice_number"))
    missing = FieldAlias(_selector(module, "missing"), FieldKey("other"))
    first_alias = FieldAlias(_selector(module, "invoice_number"), FieldKey("number"))
    second_alias = FieldAlias(_selector(module, "invoice_number"), FieldKey("document_number"))

    missing_result = resolve_schema(_schema(module), (missing,))
    repeated_result = resolve_schema(_schema(module), (second_alias, first_alias))

    assert missing_result.conflicts[0].code is CompositionConflictCode.MISSING_FIELD
    assert repeated_result.conflicts[0].code is CompositionConflictCode.INVALID_DIRECTIVE


def test_directive_order_is_canonical_for_resolved_identity() -> None:
    first = _module("00000000-0000-4000-8000-000000000001", "first", _field("legacy_one"))
    second = _module("00000000-0000-4000-8000-000000000002", "second", _field("legacy_two"))
    directives = (
        FieldAlias(_selector(first, "legacy_one"), FieldKey("canonical_one")),
        FieldAlias(_selector(second, "legacy_two"), FieldKey("canonical_two")),
    )

    forward = resolve_schema(_schema(second, first), directives).resolved
    reverse = resolve_schema(_schema(first, second), tuple(reversed(directives))).resolved

    assert forward is not None
    assert reverse is not None
    assert forward.identity == reverse.identity
    assert forward.directives == reverse.directives
