# Schema persistence

TASK-010 and TASK-011 establish the first durable bounded-context storage in Evidentia. The schemas module owns its SQLAlchemy records, Alembic versions, PostgreSQL namespace, repository ports, and adapters. Domain objects remain unaware of SQLAlchemy.

## Storage model

`evidentia_schemas.schema_drafts` holds mutable tenant-scoped working copies. A `(tenant_id, schema_id)` key identifies one draft, while a positive `revision` supports compare-and-swap updates. The canonical draft envelope is JSONB so field structures remain dynamic; tenant, identity, concurrency, audit, and timestamp values remain relational.

`evidentia_schemas.schema_publications` holds immutable canonical snapshots under `(tenant_id, schema_id, version)`. It retains the content digest, previous version, compatibility evidence, publication actor, correlation identifier, acknowledgement, and server-aware publication time. PostgreSQL triggers reject updates and deletes.

`evidentia_schemas.schema_publication_artifacts` normalizes every versioned artifact reference and its binding path for integrity checks and efficient queries. The canonical snapshot remains the source of truth; repository loads reject any disagreement between the snapshot and normalized evidence.

## Repository boundary

The application-layer `SchemaRepository` protocol contains no SQLAlchemy types. The PostgreSQL adapter always filters reads and writes by tenant plus aggregate identity. A record existing under another tenant is indistinguishable from a missing record.

Draft updates include the expected revision in the SQL predicate and increment it atomically. A missing tenant-scoped row raises a not-found failure; a matching row with a different revision raises a concurrency conflict.

Publication and artifact inserts execute inside one savepoint within the caller-owned transaction. The repository flushes but never commits, allowing the eventual API or worker use case to coordinate its complete transaction explicitly. Duplicate published versions become a stable application-layer conflict.

## Future isolation

Tenant-scoped keys and constraints are mandatory now. PostgreSQL row-level security remains deferred until authenticated tenant identity can be set reliably on every database session; adding it later will reinforce rather than replace repository scoping.
