# Evidentia interaction-first delivery roadmap

Status: Accepted  
Governing ADRs: `9M0TE8Z5N6VWW459X5N1P7EG95`, `GC27J7X510394MDYVWSK5M14C2`

## Planning rule

Evidentia keeps its complete product scope, but implementation proceeds through usable product checkpoints. Each checkpoint is a production-shaped vertical slice, not a proof of concept or throwaway prototype.

Detailed tasks and subtasks exist only for the active story and the immediately upcoming story. Later capabilities stay visible as stories with activation conditions. Persistence, OCR, queues, realtime, cloud adapters, enterprise identity, Delibera, and other infrastructure are introduced when a user-facing capability first needs them.

## Checkpoint 1 — Interactive Schema Workbench

Skyhook epic: `37GEDS1AHPKD75TVFA4TGN1VD4`

Outcome: an administrator can sign in and create, validate, compare, publish, and compose dynamic document schemas through the browser.

Ordered stories:

1. `4PJTJVE73D2MN7GT64T48S05HT` — complete the reusable schema lifecycle domain;
2. persist governed schemas for interactive use;
3. establish the minimum trusted operator and tenant context;
4. expose the governed schema lifecycle through a versioned API;
5. build the accessible Schema Workbench;
6. prove the complete draft-to-published journey.

Activation notes:

- the PostgreSQL workflow is a user-approved decision gate before migrations or integration work;
- enterprise OIDC is not required for the local checkpoint;
- no worker, queue, OCR service, object-store service, or realtime transport is required.

## Checkpoint 2 — Document Intake and Source Viewer

Skyhook epic: `JA6EY894YZ69F5JN40GG143M2S`

Outcome: a user can upload a document, preserve the original, follow processing, and inspect its page and text representation.

Stories cover original upload, native parsing, conditional OCR, and the source-viewer checkpoint.

Activation notes:

- local storage is the first adapter; cloud object storage waits for a deployment need;
- native-text parsing comes first;
- OCR activates only when representative scanned documents enter the supported corpus;
- durable background jobs activate only when measured duration, throughput, retry, or recovery needs exceed the synchronous/local path.

## Checkpoint 3 — Evidence-backed Extraction and Review

Skyhook epic: `78QQ2PHQ2E1QHQV03FFBCXYRQD`

Outcome: Evidentia resolves a governed schema, creates an evidence-linked candidate record, explains validation findings, supports correction, and submits an immutable revision.

Stories cover schema resolution, extraction, evidence, validation, review, and immutable submission.

Activation notes:

- extraction stays behind a provider-neutral port;
- fields, groups, and tables are rendered from schema metadata rather than document-specific code;
- automatic schema discovery waits for enough real corrections and examples to evaluate it responsibly.

## Checkpoint 4 — Approval and Authorized Delivery

Skyhook epic: `NNEY4EH15NKW1PZK4G75T8CJ99`

Outcome: an exact submitted revision can be approved and delivered through a versioned destination mapping with idempotency and audit evidence.

Stories cover approval semantics, local approval, mappings, authorized delivery, and optional Delibera.

Activation notes:

- secure local approval is the default independent path;
- Delibera is an optional `ApprovalAdapter` activated only after the generic contract works and an integration scope is approved;
- outbox/inbox infrastructure is introduced only if an external reliability boundary creates a concrete dual-write or ambiguous-outcome risk.

## Checkpoint 5 — Collaboration and Operational Scale

Skyhook epic: `MGTBBJH7794WRYSFBFE6ZYWXCV`

Outcome: Evidentia can support multiple operators, larger workloads, richer document relationships, and safe operational recovery.

Stories cover collaboration, conditional realtime, conditional jobs and reconciliation, advanced workflows, and operations.

Activation notes:

- realtime transport is chosen only when concurrent collaboration needs it; Firebase and sockets are compared then;
- durable queues are chosen only from measured workload and reliability requirements;
- batch, connectors, bundles, and matching require named use cases and representative data;
- an operations workspace follows real deployed recovery needs.

## Checkpoint 6 — Production, Ecosystem, and Release Evidence

Skyhook epic: `89QP3HS2PDE09EJ9X86P5QRFWM`

Outcome: supported deployments have appropriate identity, privacy, recovery, extension, evaluation, and release evidence.

Stories cover production security, public contracts, extension contracts, deployment lifecycle, and release evidence.

Activation notes:

- enterprise identity and privacy controls start from a selected deployment and threat model;
- public APIs, SDKs, and adapter contracts are published after product contracts prove stable;
- deployment packaging is separate from the local developer workflow;
- evaluation claims use permission-cleared representative data and disclose limitations.

## Readiness and decomposition rules

A story moves to `ready` only when its dependencies and unresolved decisions are settled, its acceptance criteria describe an observable outcome, and it is small enough to review coherently.

Before implementation:

1. verify the governing requirements, standards, ADRs, and module boundaries;
2. decompose only the active story and its immediate successor into reviewable tasks;
3. state each task's feature, purpose, contribution, evidence, and out-of-scope boundary;
4. make dependencies acyclic and mark only the first executable task `ready`;
5. lease the work in Skyhook and ask the user for implementation approval.

Superseded capability-first stories and their premature implementation passes remain in Skyhook as cancelled history; they are not deleted and do not represent abandoned scope.
