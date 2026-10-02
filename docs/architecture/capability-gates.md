# Evidentia Capability Gates

Status: Accepted  
Governing ADR: `9M0TE8Z5N6VWW459X5N1P7EG95`

## Purpose

Evidentia is planned as the complete product from the outset, but implementation proceeds through capability gates. A gate is not a reduced product promise or throwaway prototype. It is an independently verifiable layer of the final architecture that enables the next layer without weakening traceability, tenant isolation, durability, extensibility, or operability.

Stories may be developed in parallel when their declared dependencies permit it. A later gate cannot be declared complete while an earlier gate's exit criteria are failing.

## Gate 0 — Executable platform foundation

Outcome: a reproducible, tenant-aware API, worker, web application, PostgreSQL runtime, public-contract workflow, and quality pipeline exist before business workflows accumulate.

Skyhook epic: `CG7VFRWAF177CMZK333E19YND1`

Ordered stories:

1. `STORY-007` — bootstrap the governed monorepo and locked toolchains;
2. `STORY-008` — create bounded-context package skeletons and boundary tests;
3. `STORY-009` — establish secure configuration and the local Compose runtime;
4. `STORY-010` — build module-owned migrations and tenant-safe persistence primitives;
5. `STORY-011` — implement trusted identity, tenant context, and authorization hooks;
6. `STORY-012` — establish API, error, correlation, and OpenAPI conventions;
7. `STORY-013` — build the accessible application shell and generated-client boundary;
8. `STORY-014` — create the worker composition root and durable-work port;
9. `STORY-015` — implement provider-neutral continuous-quality and supply-chain gates;
10. `STORY-016` — prove the API-worker-web walking skeleton.

Exit criteria:

- a fresh checkout can reproduce dependencies, migrations, generated contracts, SDKs, and builds;
- the local Compose profile starts healthy API, worker, web, PostgreSQL, and local-storage components;
- authentication establishes trusted tenant context for API and worker execution;
- automated tests demonstrate denial of cross-tenant access;
- module-boundary, type, lint, test, OpenAPI-compatibility, generated-file, and security gates pass;
- the browser shell communicates only through the supported generated client;
- the runbook clearly distinguishes enabled capabilities from later product gates.

## Gate 1 — Trusted ingestion and source representation

Outcome: Evidentia can safely receive supported document inputs, preserve originals, schedule durable work, and produce inspectable source representations without trusting document content.

Primary stories:

- `KMC5EK26PXNT868PT6W97RX06A` — document and artifact storage adapters;
- `D86X3Q727TBSXDQX5NRNNZEB63` — interactive and asynchronous ingestion;
- `C37NZW5X9ASZRS7XHZ7W56MG8V` — parser and OCR adapter contracts;
- `DC2ZQWDS83EVZ95JRJERYN90RP` — durable job execution;
- `BNPAYSRAD7TJQ56MBQRP1BAHJQ` — outbox, inbox, and reconciliation;
- `36P0MN74XTPQ943H6EVXGDX1WE` — secure untrusted-document processing.

Exit criteria include original-byte integrity, deduplication, tenant-safe storage keys, limit enforcement, malware/active-content boundaries, durable retry and cancellation, native/scanned source representations, and recovery after interrupted work.

## Gate 2 — Dynamic extraction, schemas, and evidence

Outcome: versioned schemas are resolved or composed deterministically, interchangeable providers produce candidate values, and every material value can retain structured evidence and provenance.

Primary stories:

- `4PJTJVE73D2MN7GT64T48S05HT` — versioned schema lifecycle;
- `STORY-002` — contextual schema resolution and composition;
- `RXAZEMKJVJNN58W029T397M3QN` — classification and correction;
- `BYNGTQS6SX4FB7HQ46D9FKTJR2` — hosted and local extraction-provider interface;
- `XPNG59AKNVHXYMPRFWR71DSE0C` — field and table evidence;
- `8PKADXET1MA10TAY9F6VBDYYAD` — reprocessing and comparison;
- `STORY-003` — governed schema discovery and evolution.

Exit criteria include immutable published schema versions, exact decimal handling, persisted resolution context, raw and normalized provider outputs, unmapped candidates, evidence locators, provider-independent conformance fixtures, and reproducible reprocessing comparisons.

## Gate 3 — Validation and collaborative review

Outcome: users can understand findings, correct records without silent overwrites, collaborate efficiently, and submit immutable record revisions.

Primary stories:

- `06SRF2HBM8APTGA5RP2D9XS3JP` — versioned validation engine;
- `ASQKQ6YH4S8G6SDQ6XN7BHYM8E` — document-and-record review workspace;
- `3J2M9KAE9H8THGD2AR9DSKXYTC` — collaboration and conflict handling;
- `B1B7G0DXYE4JSEGFSC2NT8MFD1` — immutable submission and supersession;
- `WJN4QJFCJQ98V9Q35KDDVW0HGN` — prioritized exception queues.

Exit criteria include explainable blocking/advisory findings, accessible keyboard-oriented editing, correction provenance, optimistic conflict detection, assignments/comments, immutable submission, and complete supersession history.

## Gate 4 — Revision-bound authorization and recoverable delivery

Outcome: an exact submitted revision can be authorized locally and delivered through a versioned adapter with idempotency, retries, and reconciliation.

Primary stories:

- `Q2840JNY2G50TCZHWY7MWRBKHT` — ApprovalAdapter semantics;
- `NWMGM72BETT2BVW6DPW6APQCGR` — secure local/manual approval;
- `FK5B70RZFH4QSTW7Y02R1D3E1N` — DestinationAdapter and mappings;
- `XRS5S2GBBCPV9Q9CCN2DXBJ2G3` — idempotent delivery orchestration;
- `0C4PR416ZZ5WCA73DMBZFK87CY` — delivery administration and recovery.

Exit criteria include retained RFC 8785 canonical payloads, versioned SHA-256 digests, authorization bound to revision and destination scope, explicit revocation/supersession behavior, no delivery without authorization, ambiguous-outcome reconciliation, and independently tracked delivery state.

## Gate 5 — Operational scale and extension ecosystem

Outcome: Evidentia supports production workload shapes and stable extension points without changing the core lifecycle.

Primary stories:

- `HFVVS2GASHC8W7HEMCW9VMP0TB` — batch and connector ingestion;
- `GAAPXNG7SK2X48CW2GDDG7MJ06` — document bundles and relationships;
- `KYSVD7PWKX5ZAZW4FN67NXA26E` — cross-document matching;
- `5DGKC77RV9C2GWTKWK49788S1B` — tables, languages, and batch operations;
- `75J1CS4ZFVG3RSXH2GDF7W82ME` — public REST and OpenAPI contracts;
- `89ZWE45CMH2MKH116P992C3BDS` — supported SDKs;
- `NGSBE5Q1QVXJG649C8FQ7JM41Y` — adapter development interfaces;
- `STORY-004` — replaceable realtime subscription port;
- `0P37MDJCQKH1STANM151Q81NHH` — optional Delibera adapter.

Delibera remains optional. Gate 5 is complete without Delibera when the generic approval conformance suite passes; the Delibera adapter has its own compatibility evidence when included.

## Gate 6 — Production evidence, privacy, and lifecycle operations

Outcome: supported releases have measured quality, observable operations, recovery procedures, configurable retention, and trustworthy public evidence.

Primary stories:

- `JY8T325XB4VZ2F6DZRPYY7XEHD` — permission-cleared evaluation program;
- `STORY-001` — first invoice benchmark and extension conformance suite;
- `1VED17WSNE77N7VVCZTXC2NAT5` — difficult-source evaluation;
- `WKW6R599VZYZS7J7V8MXGDXWZX` — observability and recovery console;
- `00B1KJ2YM4P1PBKNQTM3AWSPSP` — retention, privacy, and audit controls;
- `99JY71R6GRKG8SXDWD92357XNV` — deployment, backup, and upgrade profiles;
- `7EGC5PWY8MQB5BKQKTR05DWBPQ` — release and contributor evidence.

Exit criteria include held-out benchmark results by document class and language, bounded quality claims, provider comparisons, audit-safe retention/deletion, metrics and correlation, backup/restore rehearsal, migration and upgrade rehearsal, published limitations, and contributor-ready verification.

## Readiness rules

A story moves from `backlog` to `ready` only when:

- its dependencies are complete or explicitly represented by testable contracts;
- requirement and standard links are present;
- acceptance criteria describe observable outcomes rather than implementation activity alone;
- security, tenant, migration, compatibility, and recovery implications are addressed where applicable;
- unresolved choices cannot materially change the task's implementation;
- the story is small enough to review as one coherent change, otherwise it is decomposed before implementation.

Only the earliest dependency-free story needed for active work should be leased. Parallel leases are appropriate when stories are genuinely independent and their integration contract already exists.
