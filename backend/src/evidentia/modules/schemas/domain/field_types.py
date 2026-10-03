"""Closed core field types and their canonical scalar representations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from enum import StrEnum
from uuid import UUID

_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_TYPE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_NAMESPACE_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)


class FieldTypeKind(StrEnum):
    """Stable discriminator for every governed core field type.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    STRING = "string"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    MONEY = "money"
    DATE = "date"
    DATETIME = "datetime"
    ENUM = "enum"
    IDENTIFIER = "identifier"
    REFERENCE = "reference"
    OBJECT = "object"
    ARRAY = "array"
    TABLE = "table"
    ARTIFACT_REFERENCE = "artifact_reference"
    EXTENSION = "extension"


def _validate_count_range(minimum: int, maximum: int | None, subject: str) -> None:
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
        raise ValueError(f"{subject} minimum must be a non-negative integer")
    if maximum is not None and (
        isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < minimum
    ):
        raise ValueError(f"{subject} maximum must be an integer at least equal to minimum")


def _canonical_decimal_input(value: str | int | Decimal) -> Decimal:
    if isinstance(value, (bool, float)):
        raise ValueError("decimal values must not use boolean or binary floating-point inputs")
    text = str(value)
    if not _DECIMAL_PATTERN.fullmatch(text):
        raise ValueError("decimal value must use plain canonical decimal notation")
    try:
        parsed = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("decimal value is invalid") from error
    if not parsed.is_finite():
        raise ValueError("decimal value must be finite")
    return parsed


def _decimal_digit_count(value: Decimal, scale: int) -> int:
    integer_digits = max(value.copy_abs().adjusted() + 1, 0) if value else 0
    return integer_digits + scale


@dataclass(frozen=True, slots=True)
class StringType:
    """Unicode string type with optional length and regular-expression constraints.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    min_length: int = 0
    max_length: int | None = None
    pattern: str | None = None
    kind: FieldTypeKind = field(default=FieldTypeKind.STRING, init=False)

    def __post_init__(self) -> None:
        _validate_count_range(self.min_length, self.max_length, "string length")
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as error:
                raise ValueError("string pattern must be a valid regular expression") from error

    def canonicalize(self, value: object) -> str:
        """Validate and return a string without lossy normalization."""
        if not isinstance(value, str):
            raise ValueError("string field value must be a string")
        if len(value) < self.min_length or (
            self.max_length is not None and len(value) > self.max_length
        ):
            raise ValueError("string field value violates its length constraints")
        if self.pattern is not None and re.fullmatch(self.pattern, value) is None:
            raise ValueError("string field value does not match its required pattern")
        return value


@dataclass(frozen=True, slots=True)
class BooleanType:
    """Strict boolean type that does not coerce integers or strings.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    kind: FieldTypeKind = field(default=FieldTypeKind.BOOLEAN, init=False)

    def canonicalize(self, value: object) -> bool:
        """Return a strict boolean value."""
        if not isinstance(value, bool):
            raise ValueError("boolean field value must be a boolean")
        return value


@dataclass(frozen=True, slots=True)
class IntegerType:
    """Arbitrary-size integer type with optional inclusive bounds.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    minimum: int | None = None
    maximum: int | None = None
    kind: FieldTypeKind = field(default=FieldTypeKind.INTEGER, init=False)

    def __post_init__(self) -> None:
        for bound in (self.minimum, self.maximum):
            if bound is not None and (isinstance(bound, bool) or not isinstance(bound, int)):
                raise ValueError("integer bounds must be integers")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("integer minimum must not exceed maximum")

    def canonicalize(self, value: object) -> int:
        """Return a strict integer within the configured bounds."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("integer field value must be an integer")
        if self.minimum is not None and value < self.minimum:
            raise ValueError("integer field value is below its minimum")
        if self.maximum is not None and value > self.maximum:
            raise ValueError("integer field value is above its maximum")
        return value


@dataclass(frozen=True, slots=True)
class DecimalType:
    """Arbitrary-precision decimal type with deterministic string output.

    @skyhook-implements REQ-003
    @skyhook-implements CON-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    precision: int | None = None
    scale: int | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    kind: FieldTypeKind = field(default=FieldTypeKind.DECIMAL, init=False)

    def __post_init__(self) -> None:
        if self.precision is not None and (isinstance(self.precision, bool) or self.precision < 1):
            raise ValueError("decimal precision must be a positive integer")
        if self.scale is not None and (isinstance(self.scale, bool) or self.scale < 0):
            raise ValueError("decimal scale must be a non-negative integer")
        if self.precision is not None and self.scale is not None and self.scale > self.precision:
            raise ValueError("decimal scale must not exceed precision")
        for bound in (self.minimum, self.maximum):
            if bound is not None and (not isinstance(bound, Decimal) or not bound.is_finite()):
                raise ValueError("decimal bounds must be finite Decimal values")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("decimal minimum must not exceed maximum")

    def canonicalize(self, value: str | int | Decimal) -> str:
        """Validate a decimal and return its non-exponent canonical string."""
        parsed = _canonical_decimal_input(value)
        if self.scale is not None:
            quantum = Decimal(1).scaleb(-self.scale)
            required_precision = max(
                len(parsed.as_tuple().digits) + self.scale,
                self.precision or 0,
                self.scale + 1,
                28,
            )
            with localcontext() as context:
                context.prec = required_precision
                quantized = parsed.quantize(quantum)
            if quantized != parsed:
                raise ValueError("decimal value has more fractional digits than its scale")
            parsed = quantized
            rendered = format(parsed, f".{self.scale}f")
            digit_count = _decimal_digit_count(parsed, self.scale)
        else:
            if parsed == 0:
                parsed = Decimal(0)
            rendered = format(parsed, "f")
            if "." in rendered:
                rendered = rendered.rstrip("0").rstrip(".")
            digit_count = len(parsed.normalize().as_tuple().digits)
        if self.precision is not None and digit_count > self.precision:
            raise ValueError("decimal value exceeds its precision")
        if self.minimum is not None and parsed < self.minimum:
            raise ValueError("decimal value is below its minimum")
        if self.maximum is not None and parsed > self.maximum:
            raise ValueError("decimal value is above its maximum")
        return "0" if rendered in {"-0", ""} else rendered


@dataclass(frozen=True, slots=True)
class MoneyValue:
    """Canonical currency and arbitrary-precision amount pair.

    @skyhook-implements REQ-003
    @skyhook-implements CON-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    currency: str
    amount: str


@dataclass(frozen=True, slots=True)
class MoneyType:
    """Money type with explicit currency policy and decimal amount semantics.

    @skyhook-implements REQ-003
    @skyhook-implements CON-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    amount: DecimalType = DecimalType()
    allowed_currencies: tuple[str, ...] = ()
    kind: FieldTypeKind = field(default=FieldTypeKind.MONEY, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.amount, DecimalType):
            raise ValueError("money amount must use DecimalType")
        normalized = tuple(sorted(set(self.allowed_currencies)))
        if len(normalized) != len(self.allowed_currencies):
            raise ValueError("allowed currencies must be unique")
        if any(_CURRENCY_PATTERN.fullmatch(currency) is None for currency in normalized):
            raise ValueError("currency codes must contain exactly three uppercase ASCII letters")
        object.__setattr__(self, "allowed_currencies", normalized)

    def canonicalize(self, currency: str, amount: str | int | Decimal) -> MoneyValue:
        """Validate a currency and amount and return their canonical pair."""
        if not isinstance(currency, str) or _CURRENCY_PATTERN.fullmatch(currency) is None:
            raise ValueError("currency code must contain exactly three uppercase ASCII letters")
        if self.allowed_currencies and currency not in self.allowed_currencies:
            raise ValueError("currency code is not allowed by this field")
        return MoneyValue(currency=currency, amount=self.amount.canonicalize(amount))


@dataclass(frozen=True, slots=True)
class DateType:
    """ISO 8601 calendar-date type with canonical YYYY-MM-DD output.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    kind: FieldTypeKind = field(default=FieldTypeKind.DATE, init=False)

    def canonicalize(self, value: str | date) -> str:
        """Validate and return a canonical calendar date."""
        if isinstance(value, datetime):
            raise ValueError("date field value must not contain a time")
        if isinstance(value, date):
            return value.isoformat()
        if not isinstance(value, str):
            raise ValueError("date field value must be a date or ISO date string")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as error:
            raise ValueError("date field value must use valid YYYY-MM-DD notation") from error
        if parsed.isoformat() != value:
            raise ValueError("date field value must use canonical YYYY-MM-DD notation")
        return value


@dataclass(frozen=True, slots=True)
class DateTimeType:
    """Timezone-aware ISO 8601 instant normalized to UTC.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    kind: FieldTypeKind = field(default=FieldTypeKind.DATETIME, init=False)

    def canonicalize(self, value: str | datetime) -> str:
        """Validate an instant and return canonical UTC notation ending in ``Z``."""
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError("datetime field value must be a valid ISO 8601 instant") from error
        elif isinstance(value, datetime):
            parsed = value
        else:
            raise ValueError("datetime field value must be a datetime or ISO string")
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("datetime field value must include an explicit timezone")
        utc_value = parsed.astimezone(UTC)
        timespec = "microseconds" if utc_value.microsecond else "seconds"
        return utc_value.isoformat(timespec=timespec).replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class EnumType:
    """Closed set of stable machine values with no label coupling.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    values: tuple[str, ...]
    kind: FieldTypeKind = field(default=FieldTypeKind.ENUM, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.values, tuple):
            raise ValueError("enum values must be retained in an immutable tuple")
        if not self.values:
            raise ValueError("enum type must declare at least one value")
        if len(set(self.values)) != len(self.values):
            raise ValueError("enum values must be unique")
        if any(_TYPE_NAME_PATTERN.fullmatch(value) is None for value in self.values):
            raise ValueError("enum values must be lower-snake-case machine values")

    def canonicalize(self, value: object) -> str:
        """Return an exact declared enum value."""
        if not isinstance(value, str) or value not in self.values:
            raise ValueError("enum field value must be one of the declared values")
        return value


@dataclass(frozen=True, slots=True)
class IdentifierType:
    """Opaque textual identifier with optional exact-format constraints.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    min_length: int = 1
    max_length: int = 255
    pattern: str | None = None
    kind: FieldTypeKind = field(default=FieldTypeKind.IDENTIFIER, init=False)

    def __post_init__(self) -> None:
        _validate_count_range(self.min_length, self.max_length, "identifier length")
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as error:
                raise ValueError("identifier pattern must be a valid regular expression") from error

    def canonicalize(self, value: object) -> str:
        """Validate an identifier without case folding or trimming it."""
        if not isinstance(value, str):
            raise ValueError("identifier field value must be a string")
        if value != value.strip() or len(value) < self.min_length or len(value) > self.max_length:
            raise ValueError("identifier field value violates its length or padding constraints")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("identifier field value must not contain control characters")
        if self.pattern is not None and re.fullmatch(self.pattern, value) is None:
            raise ValueError("identifier field value does not match its required pattern")
        return value


@dataclass(frozen=True, slots=True)
class ReferenceValue:
    """Canonical reference to an entity identified outside the schema definition.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    target: str
    identifier: str


@dataclass(frozen=True, slots=True)
class ReferenceType:
    """Reference type with an explicit stable target namespace.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    target: str
    identifier: IdentifierType = IdentifierType()
    kind: FieldTypeKind = field(default=FieldTypeKind.REFERENCE, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.target, str) or _TYPE_NAME_PATTERN.fullmatch(self.target) is None:
            raise ValueError("reference target must be a lower-snake-case machine value")
        if not isinstance(self.identifier, IdentifierType):
            raise ValueError("reference identifier must use IdentifierType")

    def canonicalize(self, value: object) -> ReferenceValue:
        """Validate an external identifier and bind it to this reference target."""
        return ReferenceValue(target=self.target, identifier=self.identifier.canonicalize(value))


@dataclass(frozen=True, slots=True)
class ObjectType:
    """Object container marker; Pass 2 supplies its versioned child definitions.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    min_properties: int = 0
    max_properties: int | None = None
    kind: FieldTypeKind = field(default=FieldTypeKind.OBJECT, init=False)

    def __post_init__(self) -> None:
        _validate_count_range(self.min_properties, self.max_properties, "object property count")


@dataclass(frozen=True, slots=True)
class ArrayType:
    """Array container marker; Pass 2 supplies its versioned item definition.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    min_items: int = 0
    max_items: int | None = None
    unique_items: bool = False
    kind: FieldTypeKind = field(default=FieldTypeKind.ARRAY, init=False)

    def __post_init__(self) -> None:
        _validate_count_range(self.min_items, self.max_items, "array item count")
        if not isinstance(self.unique_items, bool):
            raise ValueError("array unique-items flag must be a boolean")


@dataclass(frozen=True, slots=True)
class TableType:
    """Line-item table marker; Pass 2 supplies its versioned column definitions.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    min_rows: int = 0
    max_rows: int | None = None
    kind: FieldTypeKind = field(default=FieldTypeKind.TABLE, init=False)

    def __post_init__(self) -> None:
        _validate_count_range(self.min_rows, self.max_rows, "table row count")


@dataclass(frozen=True, slots=True)
class ArtifactReferenceValue:
    """Opaque canonical reference to a document artifact owned by another context.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    artifact_id: str


@dataclass(frozen=True, slots=True)
class ArtifactReferenceType:
    """Artifact reference that avoids importing another bounded context's internals.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    kind: FieldTypeKind = field(default=FieldTypeKind.ARTIFACT_REFERENCE, init=False)

    def canonicalize(self, value: object) -> ArtifactReferenceValue:
        """Validate and canonicalize an opaque UUID artifact identity."""
        if not isinstance(value, str):
            raise ValueError("artifact reference must be a UUID string")
        try:
            canonical = str(UUID(value))
        except ValueError as error:
            raise ValueError("artifact reference must be a valid UUID") from error
        return ArtifactReferenceValue(canonical)


@dataclass(frozen=True, slots=True)
class ExtensionType:
    """Versioned namespaced type declaration with no executable runtime payload.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    namespace: str
    name: str
    version: int
    kind: FieldTypeKind = field(default=FieldTypeKind.EXTENSION, init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.namespace, str)
            or _NAMESPACE_PATTERN.fullmatch(self.namespace) is None
        ):
            raise ValueError("extension namespace must use reverse-domain notation")
        if not isinstance(self.name, str) or _TYPE_NAME_PATTERN.fullmatch(self.name) is None:
            raise ValueError("extension name must be a lower-snake-case machine value")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("extension version must be a positive integer")
