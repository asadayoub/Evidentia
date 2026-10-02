# Evidentia Repository Structure

Status: Accepted  
Skyhook story: `STORY-005`

## Decision summary

Evidentia uses one product monorepo containing its Python backend, React frontend, public contracts, generated and supported SDKs, tests, evaluation fixtures, deployment assets, and documentation. The backend API and worker are separately runnable and deployable entry points built from the same bounded-context packages.

Delibera remains a separate repository, product, database, deployment, and release cycle. Evidentia contains only its own `ApprovalAdapter`, public compatibility fixtures, and optional Delibera adapter implementation.

## Target layout

```text
Evidentia/
├── backend/
│   ├── pyproject.toml
│   ├── src/evidentia/
│   │   ├── entrypoints/
│   │   │   ├── api/
│   │   │   └── worker/
│   │   ├── modules/
│   │   │   ├── access/
│   │   │   ├── documents/
│   │   │   ├── schemas/
│   │   │   ├── processing/
│   │   │   ├── records/
│   │   │   ├── validation/
│   │   │   ├── review/
│   │   │   ├── authorization/
│   │   │   ├── delivery/
│   │   │   ├── operations/
│   │   │   └── evaluation/
│   │   ├── adapters/
│   │   └── shared/
│   ├── migrations/
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   ├── features/
│   │   ├── components/
│   │   ├── design-system/
│   │   └── generated/
│   └── tests/
├── contracts/
│   ├── openapi/
│   ├── events/
│   ├── snapshots/
│   └── fixtures/
├── sdks/
│   ├── python/
│   └── typescript/
├── tests/
│   ├── contract/
│   ├── integration/
│   ├── end-to-end/
│   ├── architecture/
│   └── performance/
├── fixtures/
│   ├── synthetic/
│   ├── evaluation/
│   └── manifests/
├── infra/
│   ├── compose/
│   ├── containers/
│   ├── migrations/
│   └── deployment/
├── ci/
├── tools/
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── operations/
│   ├── security/
│   └── contributing/
├── .skyhook/
├── AGENTS.md
└── README.md
```

Directories are created when their first governed artifact is implemented. Empty placeholder trees are not required.

## Backend package shape

Each directory under `backend/src/evidentia/modules/` corresponds to exactly one bounded context from `docs/architecture/domain-boundaries.md`.

A module may use this internal shape where useful:

```text
module_name/
├── domain/          # Entities, value objects, domain services and transitions
├── application/     # Commands, queries, use cases and public ports
├── infrastructure/  # Module-owned repositories and adapter implementations
├── contracts/       # Public DTOs and versioned event payloads
└── public.py         # Deliberately exported application surface
```

Rules:

- Only the module's declared public surface may be imported by another module.
- Domain code imports neither application/infrastructure code nor frameworks.
- Module persistence models, repositories, tables, and migrations are private.
- The exact internal folders may be simplified when a module is small, but ownership and dependency direction do not change.
- Exported Python symbols include Skyhook traceability docstrings when they implement a requirement or story.

## Entrypoints and deployables

### API

`backend/src/evidentia/entrypoints/api/` owns FastAPI composition, transport validation, authentication middleware, dependency wiring, error mapping, and route registration. Routes call module application ports and contain no domain decisions or cross-module persistence logic.

### Worker

`backend/src/evidentia/entrypoints/worker/` owns worker startup, job and event dispatch, lease context, graceful shutdown, and adapter wiring. Handlers re-establish tenant and actor/system context and invoke module application ports.

### Frontend

`frontend/` is a React and TypeScript application built with Vite. It consumes the supported TypeScript client generated from the checked public API contract. Frontend feature folders follow user workflows and need not reproduce backend package boundaries, but they never bypass API authorization or treat local/realtime state as authoritative.

### Deployment outputs

The repository can produce independently deployable artifacts:

- Evidentia API image
- Evidentia worker image
- Evidentia web image or static build
- database migration job or command
- Python SDK package
- TypeScript SDK package

They may be versioned and released together initially without requiring the same runtime scaling or process lifecycle.

## Public contracts

`contracts/` contains reviewed, versioned, language-neutral interoperability artifacts:

- `openapi/`: checked API specifications and compatibility baselines;
- `events/`: event envelopes and payload schemas;
- `snapshots/`: authorization snapshot schemas and canonicalization fixtures;
- `fixtures/`: positive and negative contract examples shared across implementations.

The backend implementation and checked OpenAPI artifact must agree. The exact design-first or generated-and-diffed workflow is selected in a development-tooling decision, but neither side may drift silently.

SDKs are generated or implemented from checked public contracts, not from private backend models. Generated files carry headers identifying their generator and source contract and are never hand-edited.

## SDK ownership

`sdks/python/` and `sdks/typescript/` contain supported public clients, generated models, ergonomic wrappers, authentication helpers, retry/idempotency behavior, and their own tests and packaging metadata.

SDKs do not import backend domain or persistence packages. Compatibility is verified against released or checked contract versions.

## Test ownership

- Backend unit tests live under `backend/tests/` and mirror module ownership.
- Frontend unit and component tests live under `frontend/tests/` or beside components according to the selected frontend tooling convention.
- Cross-language contract tests live under `tests/contract/`.
- PostgreSQL, object-storage, and provider-adapter tests live under `tests/integration/`.
- Complete browser and API journeys live under `tests/end-to-end/`.
- Import, cycle, domain-purity, and persistence-ownership checks live under `tests/architecture/`.
- Measured workload and recovery tests live under `tests/performance/`.

Tests may import public test-support utilities. Production modules do not import test fixtures or test-only helpers.

## Evaluation fixtures and sensitive data

`fixtures/` contains only permission-cleared or synthetic material suitable for the repository.

- Every evaluation fixture has a manifest recording provenance, permission, document class, language, format, source quality, labels, and intended use.
- Sensitive customer documents are never committed by default.
- Private evaluation datasets use external storage and checked manifests or local configuration that does not expose content or credentials.
- Ground-truth annotations and benchmark configurations are versioned independently from provider outputs.

## Infrastructure and CI

`infra/` owns Docker Compose definitions, container build files, migration execution, deployment examples, health checks, backup/restore assets, and environment templates.

`ci/` owns provider-neutral scripts and configuration used for formatting, linting, type checking, tests, contract diffs, generated-file checks, architecture checks, security checks, and builds. A CI-provider directory such as `.github/workflows/` may call these scripts after repository hosting is selected; business validation is not embedded only in provider-specific YAML.

## Documentation ownership

- Architecture and ADR-supporting specifications live in `docs/architecture/`.
- Public API and SDK guidance lives in `docs/api/`.
- Installation, recovery, backup, upgrade, and observability guidance lives in `docs/operations/`.
- Threat models, disclosure guidance, and security configuration live in `docs/security/`.
- Contributor setup and repository conventions live in `docs/contributing/`.
- Skyhook remains the governed source for requirements, backlog, standards, decisions, plans, and traceability.

## Source and generated artifact rules

- Every generated artifact identifies its source contract and generator version.
- Generated artifacts are reproducible in CI and checked for unexpected diffs.
- Generated files are not manually edited.
- Build outputs, caches, local documents, secrets, and private datasets are excluded from version control.
- Public contract changes require compatibility review, regenerated SDKs, conformance tests, and release notes.
- Database migrations are append-only after release and remain owned by one bounded context.

## Delibera boundary

This repository may contain:

- Evidentia's generic `ApprovalAdapter` port;
- the optional Delibera adapter implementation;
- public request, event, signature, and compatibility fixtures;
- combined-deployment examples referencing published Delibera releases.

This repository must not contain:

- Delibera domain or persistence code;
- Delibera database migrations;
- direct queries of Delibera storage;
- copied private implementation packages;
- assumptions that both products release or deploy together.

An integrated example pins compatible public versions and communicates only through authenticated versioned contracts.

## Deferred tooling decisions

This structure deliberately does not yet select:

- Python and Node package managers;
- supported runtime versions;
- ORM and migration libraries;
- worker runtime;
- OpenAPI generator and contract-diff tools;
- lint, formatting, type-checking, and test frameworks;
- CI hosting provider;
- deployment orchestrator beyond Docker Compose-first support.

Those choices become explicit ADRs and task acceptance criteria during the development-foundation step.
