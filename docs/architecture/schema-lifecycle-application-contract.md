# Schema lifecycle application contract

The Schema Registry owns draft editing and immutable publication. HTTP routes,
workers, and future administrator interfaces call its application service; they
do not construct publication versions, tenant identifiers, actor identifiers,
or persistence records themselves.

## Authority boundary

Every operation receives a schema-owned `SchemaCommandContext`. An interface
adapter may construct it only from an authenticated, tenant-bound principal
such as Access's `TrustedRequestContext`; request bodies and headers are never
authority sources. This translation keeps the bounded contexts independent
while the Schema Registry derives tenant, actor, capabilities, and correlation
identifiers exclusively from verified context.

- `schemas.read` permits draft and exact-publication queries.
- `schemas.write` permits draft creation and canonical replacement.
- `schemas.publish` permits immutable publication.

These capabilities are independent and fail closed. A resource under another
tenant is indistinguishable from a missing resource.

## Draft contract

The client supplies only dynamic schema content: typed fields, published module
references, release label, and published artifact bindings. On creation, the
server generates the stable schema ID and assigns target version 1.

Updates replace the complete canonical draft and require `expected_revision`.
The repository atomically compares and increments that revision. This avoids
ambiguous partial patches across nested fields, arrays, tables, modules, and
artifact bindings. A stale editor receives a revision conflict and must reload,
compare, and explicitly reapply its changes.

## Publication contract

Publication requires the last observed draft revision. The application service:

1. loads the latest tenant-scoped immutable publication;
2. assigns exactly the next integer version;
3. resolves referenced artifact digests through a tenant-aware port;
4. computes compatibility against the previous immutable snapshot;
5. requires an acknowledgement for behavior-changing or breaking changes;
6. inserts the immutable publication with actor and correlation provenance;
7. advances the mutable draft to the next target version and revision.

Steps 1–7 execute inside one caller-owned database transaction. The service
never commits independently. A competing publication is resolved by optimistic
draft revision and the existing tenant/schema/version primary key; only one can
commit.

A successful publication advances the draft revision, so an immediate retry of
the same command conflicts instead of silently publishing another version.
Draft replacement and publication are therefore safely conditional. Creation
is not safe for blind transport retry until the versioned HTTP boundary provides
a durable idempotency contract.

## Persistence impact

This contract reuses the existing `schema_drafts`, `schema_publications`, and
`schema_publication_artifacts` tables. Deterministic latest-publication lookup is
added to the repository port and PostgreSQL adapter. No migration, schema
rewrite, or existing-data mutation is required for this pass.

Import, export, comparison presentation, deprecation, retirement, discovery,
and representative-document validation remain separate lifecycle stories. The
canonical types and immutable snapshots established here are designed to
support those capabilities without adding static document fields.
