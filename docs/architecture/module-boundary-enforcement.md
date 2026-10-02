# Module boundary enforcement

Status: Accepted implementation of `STORY-008`  
Related requirement: `NFR-008`  
Governing decision: `340E8TW17RVJWGK419D1K59NWK`

## Purpose

Evidentia enforces its modular-monolith boundaries in executable checks. The checks keep framework and infrastructure details out of domain code, prevent entrypoint inversion, restrict cross-context imports to deliberate public surfaces, enforce the accepted collaboration map, and reject dependency cycles.

## Context packages and public surfaces

The authoritative Python package names are:

| Bounded context        | Package         | Purpose of its eventual public surface                               |
| ---------------------- | --------------- | -------------------------------------------------------------------- |
| Access and Tenancy     | `access`        | Trusted principal, tenant, membership, and permission operations     |
| Documents              | `documents`     | Document custody, artifacts, ingestion, and relationships            |
| Schema Registry        | `schemas`       | Dynamic schema lifecycle, composition, resolution, and publication   |
| Processing             | `processing`    | Parsing, OCR, classification, extraction, and processing attempts    |
| Record Lifecycle       | `records`       | Immutable revisions, corrections, evidence, and canonical snapshots  |
| Validation             | `validation`    | Versioned rules, findings, validation runs, and overrides            |
| Review                 | `review`        | Assignments, draft workspaces, comments, and review queues           |
| Business Authorization | `authorization` | Approval requests, decisions, grants, and approval adapters          |
| Delivery               | `delivery`      | Destination mappings, delivery operations, and reconciliation        |
| Operations             | `operations`    | Durable execution, events, audit, health, and recovery               |
| Evaluation             | `evaluation`    | Permission-safe datasets, evaluations, metrics, and release evidence |

Every context has an importable `public.py`. These modules are intentionally empty until a governed story introduces a real application port, read contract, immutable snapshot, or versioned event. Internal layers are created only when they own real artifacts.

Another context must import the exact path `evidentia.modules.<context>.public`. Context package roots do not re-export public symbols. Entrypoints may compose any public surface.

## Allowed collaboration matrix

| Caller                 | May depend on public surfaces of                                             |
| ---------------------- | ---------------------------------------------------------------------------- |
| Access and Tenancy     | none                                                                         |
| Documents              | none                                                                         |
| Schema Registry        | none                                                                         |
| Processing             | Documents, Schema Registry                                                   |
| Record Lifecycle       | Processing, Schema Registry                                                  |
| Validation             | Record Lifecycle, Schema Registry                                            |
| Review                 | Documents, Record Lifecycle, Validation                                      |
| Business Authorization | Access and Tenancy, Record Lifecycle                                         |
| Delivery               | Business Authorization, Record Lifecycle                                     |
| Operations             | every bounded context through public ports or events                         |
| Evaluation             | Access, Documents, Schema Registry, Processing, Record Lifecycle, Validation |

Changing this matrix is an architectural change. Update `docs/architecture/domain-boundaries.md`, record or supersede the governing ADR in Skyhook, update the executable matrix, and add positive and negative tests in the same change.

## Enforced rules

`Import Linter` independently rejects any dependency from `evidentia.modules` to `evidentia.entrypoints` and detects cycles among bounded-context siblings.

`tools/check_architecture.py` additionally verifies:

- every accepted context has an importable package and documented `public.py`;
- domain code does not import FastAPI, SQLAlchemy, Uvicorn, entrypoints, adapters, or infrastructure code;
- cross-context imports target only the exact `public.py` surface;
- the caller-target pair is present in the collaboration matrix;
- the resulting context dependency graph is acyclic.

Run all boundary checks with:

```shell
make architecture-check
```

The same checks run inside `make lint` and the provider-neutral `ci/check.sh` workflow.
