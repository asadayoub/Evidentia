# Access persistence

The Access and Tenancy bounded context owns the `evidentia_access` PostgreSQL schema. It
stores operators, tenants, memberships, dynamic capability grants, provider identity
mappings, local password verifiers, and revocable sessions. No table has a foreign key
to another bounded context.

## Security model

- Login identifiers and tenant slugs are normalized before persistence and unique.
- Capabilities are normalized rows, allowing new permissions without schema changes.
- Local credentials contain only encoded Argon2id verifiers; plaintext passwords are
  never accepted by a repository.
- Sessions contain only lowercase SHA-256 token digests. Raw bearer tokens remain at the
  HTTP boundary and cannot be reconstructed from the database.
- Session expiry, revocation, replacement, and optional active-tenant selection are
  durable metadata. Application services remain responsible for verifying that an
  active tenant has a current active membership.

## Transaction and migration ownership

Repository adapters flush but do not commit, so application services own transaction
boundaries. The access Alembic branch is independent from other module branches and can
be upgraded or downgraded without altering their schemas. Native PostgreSQL integration
tests use a disposable migrated database to prove durability, tenant-isolated lookup,
expiry and revocation behavior, and branch reversibility.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
