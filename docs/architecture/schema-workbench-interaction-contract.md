# Schema Workbench interaction contract

The Schema Workbench is a browser adapter over the schemas bounded context. It owns no
schema lifecycle authority and does not reproduce backend domain rules. The generated
SDK is its only API transport; the API derives tenant, actor, schema identity, publication
version, audit metadata, and server timestamps.

## Interaction model

- `/app/schemas` is the tenant-scoped collection and creation surface.
- `/app/schemas/:schemaId` is the focused editor for one mutable draft.
- A visual hierarchical builder is the primary interface. Raw JSON is not required for
  normal creation, editing, or publication.
- Save is explicit. Unsaved changes are visible and publication is unavailable until the
  current draft is saved and valid.
- Publication requires an explicit confirmation that identifies the immutable version to
  be created. A successful publication leaves the user in the advanced next draft.
- A revision conflict never overwrites remote work. The editor offers Reload current
  draft; automatic merge is deferred until a governed merge model exists.

## Extensibility

One field-type registry defines labels, descriptions, child structure, default dynamic
configuration, and whether direct visual creation is currently supported. It contains all
core schema type discriminators. Reference, artifact-reference, and extension fields are
preserved and rendered when loaded, but their creation waits for their governed selectors
instead of accepting arbitrary identifiers.

The workbench model recursively represents fields, object fields, array items, and table
columns. Dynamic type configuration and artifact bindings stay JSON-safe and lossless;
the browser does not turn document-specific fields into product-level static properties.

## Runtime boundary

Generated TypeScript types describe the HTTP contract, while `parseWorkbenchDraft`
validates every dynamic response before it enters editor state. Serialization emits only
client-owned content. It deliberately cannot emit tenant ID, actor ID, schema ID, version,
revision metadata, provenance, or timestamps.

Frontend validation provides immediate path-addressed guidance for machine keys,
duplicates, cardinality, and minimum publication content. The backend remains authoritative
for the complete canonical type system, compatibility, artifact, concurrency, and
publication rules.

## Command and cache behavior

- Queries are namespaced beneath `schemas` and invalidated after successful mutations.
- Every explicit user command receives a fresh cryptographically random idempotency key.
- Save sends the last observed revision and handles `schema_revision_conflict` visibly.
- Publish sends the last saved revision and handles acknowledgement requirements without
  fabricating acknowledgement text.
- 401 returns to login through the established shell; 403 renders a forbidden state; 404
  renders a not-found state; transient failures retain local edits and offer retry.

No new durable state or migration is required. Draft persistence, optimistic concurrency,
idempotency receipts, publication history, and audit evidence remain schema-module-owned.

@skyhook-implements REQ-003
@skyhook-implements REQ-012
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements NFR-005
@skyhook-implements NFR-008
@skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
