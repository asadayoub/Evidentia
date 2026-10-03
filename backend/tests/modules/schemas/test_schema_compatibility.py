"""Compatibility classification tests for schema publication."""

from evidentia.modules.schemas.public import (
    Cardinality,
    CompatibilityLevel,
    DecimalType,
    FieldDefinition,
    FieldKey,
    PublishedSchemaVersion,
    SchemaChangeCode,
    SchemaId,
    SchemaVersion,
    StringType,
    ValueDefinition,
    compare_schema_versions,
)

SCHEMA_ID = SchemaId("123e4567-e89b-12d3-a456-426614174000")


def _field(
    key: str, *, required: bool = False, decimal: DecimalType | None = None
) -> FieldDefinition:
    return FieldDefinition(
        FieldKey(key),
        ValueDefinition.scalar(decimal or StringType()),
        Cardinality(1 if required else 0, 1),
    )


def _schema(version: int, *fields: FieldDefinition) -> PublishedSchemaVersion:
    return PublishedSchemaVersion(SCHEMA_ID, SchemaVersion(version), fields=tuple(fields))


def test_optional_addition_is_compatible_and_ordered() -> None:
    report = compare_schema_versions(
        _schema(1, _field("supplier")),
        _schema(2, _field("supplier"), _field("currency")),
    )

    assert report.level is CompatibilityLevel.ADDITIVE_COMPATIBLE
    assert report.requires_acknowledgement is False
    assert tuple(change.code for change in report.changes) == (
        SchemaChangeCode.OPTIONAL_FIELD_ADDED,
    )


def test_removal_required_addition_and_type_change_are_breaking() -> None:
    report = compare_schema_versions(
        _schema(1, _field("legacy"), _field("total")),
        _schema(2, _field("currency", required=True), _field("total", decimal=DecimalType(12, 2))),
    )

    assert report.level is CompatibilityLevel.BREAKING
    assert report.requires_acknowledgement is True
    assert {change.code for change in report.changes} == {
        SchemaChangeCode.REQUIRED_FIELD_ADDED,
        SchemaChangeCode.FIELD_REMOVED,
        SchemaChangeCode.TYPE_CHANGED,
    }


def test_constraint_and_cardinality_changes_are_classified() -> None:
    report = compare_schema_versions(
        _schema(1, _field("amount", decimal=DecimalType(12, 2))),
        _schema(2, _field("amount", required=True, decimal=DecimalType(14, 4))),
    )

    assert report.level is CompatibilityLevel.BREAKING
    assert {change.code for change in report.changes} == {
        SchemaChangeCode.CARDINALITY_TIGHTENED,
        SchemaChangeCode.CONSTRAINT_CHANGED,
    }
