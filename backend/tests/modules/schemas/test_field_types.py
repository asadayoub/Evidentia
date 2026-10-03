"""Tests for schema identity, lifecycle, and built-in field-type contracts."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from evidentia.modules.schemas.public import (
    ArrayType,
    ArtifactReferenceType,
    BooleanType,
    DateTimeType,
    DateType,
    DecimalType,
    EnumType,
    ExtensionType,
    FieldKey,
    FieldPath,
    FieldTypeKind,
    IdentifierType,
    IntegerType,
    MoneyType,
    ObjectType,
    ReferenceType,
    ReleaseLabel,
    SchemaId,
    SchemaLifecycleState,
    SchemaModuleId,
    SchemaVersion,
    StringType,
    TableType,
    allowed_schema_transitions,
    ensure_schema_transition,
)


def test_opaque_identities_are_canonical_and_distinct_types() -> None:
    raw = "550E8400-E29B-41D4-A716-446655440000"

    assert str(SchemaId(raw)) == "550e8400-e29b-41d4-a716-446655440000"
    assert str(SchemaModuleId(raw)) == "550e8400-e29b-41d4-a716-446655440000"
    assert SchemaId(raw) != SchemaModuleId(raw)
    assert UUID(str(SchemaId.new())).version == 4
    assert UUID(str(SchemaModuleId.new())).version == 4

    with pytest.raises(ValueError, match="valid UUID"):
        SchemaId("invoice")


def test_versions_labels_keys_and_paths_preserve_machine_identity() -> None:
    version = SchemaVersion(1)
    path = FieldPath.parse("supplier.address.postal_code")

    assert version.next() == SchemaVersion(2)
    assert int(version) == 1
    assert str(ReleaseLabel("October 2026")) == "October 2026"
    assert str(path) == "supplier.address.postal_code"
    assert path.child(FieldKey("country_code")) == FieldPath.parse(
        "supplier.address.postal_code.country_code"
    )

    for invalid_version in (0, -1, True):
        with pytest.raises(ValueError, match="positive integer"):
            SchemaVersion(invalid_version)
    for invalid_key in ("InvoiceNumber", "invoice-number", " invoice_number", ""):
        with pytest.raises(ValueError, match="lower-snake-case"):
            FieldKey(invalid_key)
    with pytest.raises(ValueError, match="1 to 64"):
        ReleaseLabel(" padded ")


def test_schema_lifecycle_exposes_only_forward_governed_transitions() -> None:
    assert allowed_schema_transitions(SchemaLifecycleState.DRAFT) == {
        SchemaLifecycleState.PUBLISHED
    }
    assert allowed_schema_transitions(SchemaLifecycleState.PUBLISHED) == {
        SchemaLifecycleState.DEPRECATED
    }
    assert allowed_schema_transitions(SchemaLifecycleState.DEPRECATED) == {
        SchemaLifecycleState.RETIRED
    }
    assert not allowed_schema_transitions(SchemaLifecycleState.RETIRED)

    ensure_schema_transition(SchemaLifecycleState.DRAFT, SchemaLifecycleState.PUBLISHED)
    with pytest.raises(ValueError, match="cannot transition"):
        ensure_schema_transition(SchemaLifecycleState.PUBLISHED, SchemaLifecycleState.DRAFT)
    with pytest.raises(ValueError, match="cannot transition"):
        ensure_schema_transition(SchemaLifecycleState.RETIRED, SchemaLifecycleState.PUBLISHED)


def test_strict_scalar_types_validate_without_implicit_coercion() -> None:
    string_type = StringType(min_length=2, max_length=4, pattern=r"[A-Z]+")
    integer_type = IntegerType(minimum=-2, maximum=2)

    assert string_type.kind is FieldTypeKind.STRING
    assert string_type.canonicalize("AB") == "AB"
    assert BooleanType().canonicalize(False) is False
    assert integer_type.canonicalize(2) == 2

    with pytest.raises(ValueError, match="pattern"):
        StringType(pattern="[")
    with pytest.raises(ValueError, match="length constraints"):
        string_type.canonicalize("A")
    with pytest.raises(ValueError, match="must be a boolean"):
        BooleanType().canonicalize(1)
    with pytest.raises(ValueError, match="must be an integer"):
        integer_type.canonicalize(True)
    with pytest.raises(ValueError, match="above its maximum"):
        integer_type.canonicalize(3)


def test_decimal_type_returns_canonical_arbitrary_precision_strings() -> None:
    fixed = DecimalType(
        precision=8,
        scale=2,
        minimum=Decimal("-999.99"),
        maximum=Decimal("999.99"),
    )
    variable = DecimalType()

    assert fixed.canonicalize("12.3") == "12.30"
    assert fixed.canonicalize(Decimal("0.00")) == "0.00"
    assert variable.canonicalize("120.3400") == "120.34"
    assert variable.canonicalize("-0.0") == "0"
    assert variable.canonicalize(10**100) == "1" + ("0" * 100)

    with pytest.raises(ValueError, match="binary floating-point"):
        fixed.canonicalize(1.2)
    with pytest.raises(ValueError, match="plain canonical"):
        fixed.canonicalize("01.20")
    with pytest.raises(ValueError, match="fractional digits"):
        fixed.canonicalize("1.234")
    with pytest.raises(ValueError, match="precision"):
        DecimalType(precision=4, scale=2).canonicalize("123.45")
    with pytest.raises(ValueError, match="precision"):
        DecimalType(precision=8, scale=2).canonicalize("1" + ("0" * 100))


def test_money_type_keeps_currency_separate_from_canonical_amount() -> None:
    money_type = MoneyType(
        amount=DecimalType(precision=12, scale=2),
        allowed_currencies=("USD", "EUR"),
    )

    value = money_type.canonicalize("EUR", "1250.5")

    assert value.currency == "EUR"
    assert value.amount == "1250.50"
    assert money_type.allowed_currencies == ("EUR", "USD")
    with pytest.raises(ValueError, match="not allowed"):
        money_type.canonicalize("GBP", "1.00")
    with pytest.raises(ValueError, match="uppercase ASCII"):
        money_type.canonicalize("usd", "1.00")


def test_dates_and_datetimes_have_unambiguous_canonical_representations() -> None:
    assert DateType().canonicalize(date(2026, 10, 3)) == "2026-10-03"
    assert DateType().canonicalize("2026-10-03") == "2026-10-03"
    assert DateTimeType().canonicalize(datetime(2026, 10, 3, 12, tzinfo=UTC)) == (
        "2026-10-03T12:00:00Z"
    )
    assert DateTimeType().canonicalize("2026-10-03T17:00:00+05:00") == ("2026-10-03T12:00:00Z")
    assert (
        DateTimeType().canonicalize(
            datetime(2026, 10, 3, 17, 0, 0, 1200, tzinfo=timezone(timedelta(hours=5)))
        )
        == "2026-10-03T12:00:00.001200Z"
    )

    with pytest.raises(ValueError, match="must not contain a time"):
        DateType().canonicalize(datetime(2026, 10, 3, tzinfo=UTC))
    with pytest.raises(ValueError, match="explicit timezone"):
        DateTimeType().canonicalize("2026-10-03T12:00:00")


def test_enum_identifier_and_reference_values_are_exact_and_stable() -> None:
    enum_type = EnumType(("pending_review", "approved"))
    identifier_type = IdentifierType(pattern=r"INV-[0-9]{4}")
    reference_type = ReferenceType("supplier", identifier_type)

    assert enum_type.canonicalize("approved") == "approved"
    assert identifier_type.canonicalize("INV-0042") == "INV-0042"
    assert reference_type.canonicalize("INV-0042").target == "supplier"

    with pytest.raises(ValueError, match="declared values"):
        enum_type.canonicalize("Approved")
    with pytest.raises(ValueError, match="padding"):
        identifier_type.canonicalize(" INV-0042")
    with pytest.raises(ValueError, match="required pattern"):
        reference_type.canonicalize("0042")


def test_container_artifact_and_extension_types_enforce_structural_constraints() -> None:
    artifact_id = "550E8400-E29B-41D4-A716-446655440000"

    assert ObjectType(max_properties=5).kind is FieldTypeKind.OBJECT
    assert ArrayType(min_items=1, max_items=3, unique_items=True).kind is FieldTypeKind.ARRAY
    assert TableType(max_rows=100).kind is FieldTypeKind.TABLE
    assert ArtifactReferenceType().canonicalize(artifact_id).artifact_id == (
        "550e8400-e29b-41d4-a716-446655440000"
    )
    assert ExtensionType("org.evidentia", "postal_address", 1).kind is FieldTypeKind.EXTENSION

    with pytest.raises(ValueError, match="at least equal"):
        ArrayType(min_items=2, max_items=1)
    with pytest.raises(ValueError, match="reverse-domain"):
        ExtensionType("evidentia", "postal_address", 1)
    with pytest.raises(ValueError, match="positive integer"):
        ExtensionType("org.evidentia", "postal_address", 0)
