# Governed schema lifecycle API contract

TASK-022 exposes the schema lifecycle through `/api/v1/schemas` without allowing the
browser to supply tenant, actor, schema identity, or publication version authority.
Those values are resolved from the opaque session and durable schema state.

## Operations

- `POST /drafts` creates a server-identified draft.
- `GET /drafts` returns a deterministic cursor page with a maximum page size of 100.
- `GET /drafts/{schema_id}` returns one tenant-visible mutable snapshot.
- `PUT /drafts/{schema_id}` replaces dynamic content at an expected revision.
- `POST /drafts/{schema_id}/publications` atomically publishes and advances the draft.
- `GET /{schema_id}/versions/{version}` returns one immutable publication.

All operations use cookie-backed authenticated context and return stable error codes.
Browser mutations also require CSRF proof. Create, replace, and publish commands require
an `Idempotency-Key` of 1–128 characters.

## Retry and concurrency behavior

The schemas context owns durable command receipts keyed by tenant, operation, and
idempotency key. A command claim, domain mutation, and completed response are committed
in one transaction. A matching retry replays the original response; reuse with different
content returns `idempotency_key_reused`. Replacement and publication additionally use
the last observed draft revision and return `schema_revision_conflict` for stale writes.

The additive receipts migration creates only an empty module-owned table and does not
rewrite existing schema records.

## Dynamic content boundary

The HTTP shape fixes only the lifecycle envelope: release label, fields, modules, and
artifact bindings. Field definitions remain dynamic canonical JSON and are parsed by the
schema domain before persistence. This preserves extensibility while rejecting unknown
core types, invalid cardinality, malformed nested definitions, and invalid artifacts.

Published artifact references fail closed until a governed artifact catalog adapter is
integrated. The API never trusts artifact digests merely because a client supplied them.

## Generated client

The checked OpenAPI contract generates strict TypeScript route types and schema operation
identifiers. `createSchemaClient` adds browser credentials, correlation IDs, CSRF proof,
idempotency headers, cancellation, pagination, and stable `EvidentiaApiError` mapping.

@skyhook-implements REQ-003
@skyhook-implements REQ-012
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements NFR-008
@skyhook-story X51S43NTMRW5ASYSKJBF7FW845
