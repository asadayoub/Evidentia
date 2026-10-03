"""Public domain contracts for dynamic schema identity, lifecycle, and field types.

This surface intentionally excludes persistence, providers, and mutable aggregate
implementations. Later schema passes will extend it with versioned definition and
application-port contracts.

@skyhook-implements REQ-003
@skyhook-implements NFR-008
@skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
"""

from evidentia.modules.schemas.domain.field_types import (
    ArrayType,
    ArtifactReferenceType,
    ArtifactReferenceValue,
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
    MoneyValue,
    ObjectType,
    ReferenceType,
    ReferenceValue,
    StringType,
    TableType,
)
from evidentia.modules.schemas.domain.identity import (
    FieldKey,
    FieldPath,
    ReleaseLabel,
    SchemaId,
    SchemaModuleId,
    SchemaVersion,
)
from evidentia.modules.schemas.domain.lifecycle import (
    SchemaLifecycleState,
    allowed_schema_transitions,
    ensure_schema_transition,
)

__all__ = (
    "ArrayType",
    "ArtifactReferenceType",
    "ArtifactReferenceValue",
    "BooleanType",
    "DateTimeType",
    "DateType",
    "DecimalType",
    "EnumType",
    "ExtensionType",
    "FieldKey",
    "FieldPath",
    "FieldTypeKind",
    "IdentifierType",
    "IntegerType",
    "MoneyType",
    "MoneyValue",
    "ObjectType",
    "ReferenceType",
    "ReferenceValue",
    "ReleaseLabel",
    "SchemaId",
    "SchemaLifecycleState",
    "SchemaModuleId",
    "SchemaVersion",
    "StringType",
    "TableType",
    "allowed_schema_transitions",
    "ensure_schema_transition",
)
