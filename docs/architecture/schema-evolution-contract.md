# Schema evolution contract

Schema import, export, comparison, and evolution remain owned by the schemas bounded
context. They compose the existing canonical interchange, compatibility, draft,
publication, authorization, optimistic-concurrency, and idempotency contracts.

## Portable packages

Version 1 accepts the two existing canonical JSON envelopes:

- `evidentia.schema-draft` represents a mutable snapshot;
- `evidentia.schema` represents an immutable published snapshot.

Both are deterministic UTF-8 JSON. Package format and envelope version are validated
before schema content. Recognized extension definitions round-trip as data, but importing
them does not install or activate an extension provider.

Package schema identity and version are provenance. They never select a tenant, allocate
target identity, set a target revision, or authorize a mutation.

## Preview and apply

Inspection normalizes a package and produces its canonical SHA-256 digest and editable
content. Preview has no side effects:

- a new-draft preview reports that server identity will be allocated and makes no
  compatibility claim because no consumers exist yet;
- an existing-draft preview compares normalized content with the tenant-owned current
  draft and returns deterministically ordered additive, behavior-changing, or breaking
  changes.

Apply is a separate explicit command. It either creates a server-identified draft or
replaces an existing tenant-owned draft at the caller's observed revision. It never
changes an immutable publication and never migrates records automatically.

## Durable state

No new persistence is required. Existing schema draft revisions retain the actor and
update time; idempotent command receipts retain replay safety; immutable publications
retain their provenance and content digest. The API emits package digest, target, actor,
tenant, outcome, and correlation metadata as structured events without logging package
content.

A dedicated import aggregate or migration may be introduced later only if product needs
require resumable multi-package jobs, approval workflows, or long-lived preview records.

@skyhook-implements REQ-003
@skyhook-implements REQ-016
@skyhook-implements REQ-017
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story STORY-018
