"""Public domain contracts for dynamic schema identity, lifecycle, and field types.

This surface intentionally excludes persistence, providers, and mutable aggregate
implementations. Later schema passes will extend it with versioned definition and
application-port contracts.

@skyhook-implements REQ-003
@skyhook-implements NFR-008
@skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
"""

from evidentia.modules.schemas.application.publish_schema import (
    ArtifactKey,
    PublicationProvenance,
    SchemaDraft,
    SchemaPublication,
    publish_schema,
)
from evidentia.modules.schemas.application.resolve_schema import resolve_schema
from evidentia.modules.schemas.domain.artifact_links import (
    ArtifactBindings,
    PublishedArtifactReference,
    SchemaArtifactKind,
)
from evidentia.modules.schemas.domain.compatibility import (
    CompatibilityLevel,
    CompatibilityReport,
    SchemaChange,
    SchemaChangeCode,
    compare_schema_versions,
)
from evidentia.modules.schemas.domain.composition import (
    CompositionConflict,
    CompositionConflictCode,
    CompositionDirective,
    CompositionResult,
    FieldAlias,
    FieldMapping,
    FieldOrigin,
    FieldReplacement,
    FieldSelector,
    ResolvedSchema,
    ResolvedSchemaIdentity,
)
from evidentia.modules.schemas.domain.definitions import (
    Cardinality,
    FieldDefinition,
    FieldType,
    ValueDefinition,
    ensure_unique_root_fields,
)
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
from evidentia.modules.schemas.domain.modules import (
    PublishedSchemaModule,
    PublishedSchemaVersion,
    SchemaModuleReference,
)

__all__ = (
    "ArrayType",
    "ArtifactBindings",
    "ArtifactKey",
    "ArtifactReferenceType",
    "ArtifactReferenceValue",
    "BooleanType",
    "Cardinality",
    "CompatibilityLevel",
    "CompatibilityReport",
    "CompositionConflict",
    "CompositionConflictCode",
    "CompositionDirective",
    "CompositionResult",
    "DateTimeType",
    "DateType",
    "DecimalType",
    "EnumType",
    "ExtensionType",
    "FieldAlias",
    "FieldDefinition",
    "FieldKey",
    "FieldMapping",
    "FieldOrigin",
    "FieldPath",
    "FieldReplacement",
    "FieldSelector",
    "FieldType",
    "FieldTypeKind",
    "IdentifierType",
    "IntegerType",
    "MoneyType",
    "MoneyValue",
    "ObjectType",
    "PublicationProvenance",
    "PublishedArtifactReference",
    "PublishedSchemaModule",
    "PublishedSchemaVersion",
    "ReferenceType",
    "ReferenceValue",
    "ReleaseLabel",
    "ResolvedSchema",
    "ResolvedSchemaIdentity",
    "SchemaArtifactKind",
    "SchemaChange",
    "SchemaChangeCode",
    "SchemaDraft",
    "SchemaId",
    "SchemaLifecycleState",
    "SchemaModuleId",
    "SchemaModuleReference",
    "SchemaPublication",
    "SchemaVersion",
    "StringType",
    "TableType",
    "ValueDefinition",
    "allowed_schema_transitions",
    "compare_schema_versions",
    "ensure_schema_transition",
    "ensure_unique_root_fields",
    "publish_schema",
    "resolve_schema",
)
