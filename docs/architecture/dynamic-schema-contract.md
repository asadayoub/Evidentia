# Dynamic schema contract

Evidentia schemas are immutable, versioned, document-neutral definitions. They support nested objects, arrays, tables, exact decimal and money constraints, references, evidence expectations, and separately versioned validation, normalization, presentation, localization, and extraction artifacts.

## Publication and compatibility

A draft is publishable only when its shape is valid and every referenced artifact version is available with the expected digest. Publication creates an immutable snapshot, canonical content digest, actor, correlation identifier, timestamp, and optional risk acknowledgement. An existing `(schema_id, version)` cannot be republished.

Evolution is classified as additive-compatible, behavior-changing, or breaking. Optional additions are additive. Removals, required additions, incompatible types, and tighter cardinality are breaking. Constraint, artifact, module-selection, and relaxed-cardinality changes are behavior-changing. Behavior-changing and breaking publications require explicit acknowledgement.

## Interchange

The canonical envelope uses `format = "evidentia.schema"` and `version = 1`. Export is deterministic UTF-8 JSON. Exact decimals are strings, localized metadata remains an explicit versioned artifact reference, and recognized extension types retain namespace, name, and version. Import rejects unknown core types and unsupported envelope versions.

Future envelope versions may add compatible members or define a new versioned decoder. They must not silently reinterpret version 1 content.

## Migration and reprocessing

Migration and reprocessing are pure plans. They always identify an existing source revision and a distinct new proposed revision. Reprocessing also identifies a new extraction attempt. Neither operation mutates, replaces, or deletes the historical revision; submission, authorization, and delivery continue to reference the exact immutable revision that originally entered those lifecycles.
