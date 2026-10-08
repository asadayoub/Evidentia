"""Canonical schema interchange round-trip tests."""

import json
from decimal import Decimal

import pytest

from evidentia.modules.schemas.application.interchange import (
    export_schema_draft,
    import_schema_draft,
)
from evidentia.modules.schemas.application.publish_schema import SchemaDraft
from evidentia.modules.schemas.public import (
    ArtifactBindings,
    Cardinality,
    DecimalType,
    ExtensionType,
    FieldDefinition,
    FieldKey,
    MoneyType,
    PublishedArtifactReference,
    PublishedSchemaVersion,
    SchemaArtifactKind,
    SchemaId,
    SchemaVersion,
    StringType,
    TableType,
    ValueDefinition,
    export_schema,
    import_schema,
)


def _schema() -> PublishedSchemaVersion:
    localization = PublishedArtifactReference(
        "550e8400-e29b-41d4-a716-446655440000",
        SchemaVersion(2),
        SchemaArtifactKind.LOCALIZATION,
        "a" * 64,
    )
    lines = FieldDefinition(
        FieldKey("lines"),
        ValueDefinition.table(
            (
                FieldDefinition(
                    FieldKey("description"), ValueDefinition.scalar(StringType(1, 200))
                ),
                FieldDefinition(
                    FieldKey("amount"),
                    ValueDefinition.scalar(MoneyType(DecimalType(14, 4), ("EUR", "USD"))),
                    Cardinality(1, 1),
                ),
            ),
            field_type=TableType(1),
            artifacts=ArtifactBindings((localization,)),
        ),
    )
    extension = FieldDefinition(
        FieldKey("industry_code"),
        ValueDefinition.scalar(ExtensionType("org.example.finance", "industry_code", 3)),
    )
    return PublishedSchemaVersion(
        SchemaId("123e4567-e89b-12d3-a456-426614174000"),
        SchemaVersion(4),
        fields=(lines, extension),
    )


def test_nested_table_money_decimal_localization_and_extension_round_trip() -> None:
    schema = _schema()
    payload = export_schema(schema)

    assert export_schema(schema) == payload
    assert import_schema(payload).schema == schema
    assert b'"version":1' in payload


def test_decimal_bounds_are_canonical_strings() -> None:
    schema = PublishedSchemaVersion(
        SchemaId("123e4567-e89b-12d3-a456-426614174000"),
        SchemaVersion(1),
        fields=(
            FieldDefinition(
                FieldKey("ratio"),
                ValueDefinition.scalar(DecimalType(9, 3, Decimal("-1.250"), Decimal("2.500"))),
            ),
        ),
    )
    document = json.loads(export_schema(schema))
    field_type = document["schema"]["fields"][0]["value"]["type"]

    assert field_type["minimum"] == "-1.250"
    assert field_type["maximum"] == "2.500"
    assert import_schema(export_schema(schema)).schema == schema


def test_unknown_core_type_and_envelope_version_are_rejected() -> None:
    document = json.loads(export_schema(_schema()))
    document["schema"]["fields"][0]["value"]["type"]["kind"] = "future_core"
    with pytest.raises(ValueError, match="unknown core field type"):
        import_schema(json.dumps(document))

    document = json.loads(export_schema(_schema()))
    document["version"] = 2
    with pytest.raises(ValueError, match="unsupported schema interchange version"):
        import_schema(json.dumps(document))


def test_empty_mutable_draft_has_a_deterministic_round_trip() -> None:
    """Persist workbench drafts before their first field is defined.

    @skyhook-implements REQ-003
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    draft = SchemaDraft(
        SchemaId("123e4567-e89b-12d3-a456-426614174000"),
        SchemaVersion(1),
    )

    payload = export_schema_draft(draft)

    assert import_schema_draft(payload) == draft
    assert export_schema_draft(draft) == payload
    assert b'"format":"evidentia.schema-draft"' in payload


def test_mutable_draft_import_rejects_duplicate_root_fields_before_preview() -> None:
    """Keep invalid package content outside preview and persistence boundaries.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 265YM4FNANJAH2J338BKAWFXDM
    """
    document = json.loads(
        export_schema_draft(
            SchemaDraft(
                SchemaId("123e4567-e89b-12d3-a456-426614174000"),
                SchemaVersion(1),
                fields=(
                    FieldDefinition(
                        FieldKey("invoice_number"), ValueDefinition.scalar(StringType())
                    ),
                ),
            )
        )
    )
    document["schema"]["fields"].append(document["schema"]["fields"][0])

    with pytest.raises(ValueError, match="duplicate field keys"):
        import_schema_draft(json.dumps(document))
