# Evidentia just-in-time implementation-pass convention

Skyhook stories are governed delivery outcomes. Tasks and subtasks are reviewable implementation passes created only when a story is active or immediately upcoming.

## Task content

Every implementation task states:

- the concrete feature delivered in this pass;
- why the feature is needed now;
- how it contributes to the current user-visible checkpoint;
- the files or boundaries expected to change;
- the tests or other evidence required for completion;
- what remains explicitly out of scope;
- dependencies on accepted decisions or earlier evidence.

Exported production symbols retain the story or requirement annotations required by `AGENTS.md`. Completing child tasks does not bypass story acceptance criteria, policy checks, standards, drift checks, traceability, review, or a focused commit.

## Decomposition horizon

The full product is planned through requirements, ADRs, epics, stories, dependencies, acceptance criteria, and activation conditions. Detailed tasks are limited to:

1. the currently active story; and
2. the immediately upcoming story when its decisions are stable.

When a choice could materially change implementation, create a decision-gate task rather than speculative coding passes. After the user approves the decision, record it in Skyhook and create the implementation tasks.

## Current horizon

The completed enabling story is `4PJTJVE73D2MN7GT64T48S05HT` — **Build versioned schema lifecycle**.

| Pass | Feature | Contribution |
| --- | --- | --- |
| `TASK-002` | Schema identity, lifecycle, and core field types | Establishes the document-neutral schema vocabulary. |
| `TASK-003` | Immutable versioned schema aggregates | Represents dynamic fields, groups, tables, and governed artifact references. |
| `TASK-004` | Deterministic schema composition | Enables explainable reusable modules without silent conflicts. |
| `TASK-005` | Publication and compatibility governance | Protects immutable history and explains schema evolution. |
| `TASK-006` | Canonical interchange and migration planning | Makes schemas portable without rewriting historical records. |

The active story is `0VJ9SHA39TA291D8QXB0TQS3HQ` — **Persist governed schemas for interactive use**.

| Pass | Feature | Contribution |
| --- | --- | --- |
| `TASK-007` | Native-versus-container runtime decision | Selects native PostgreSQL 16.x now and defers the optional hybrid profile. |
| `TASK-009` | Native PostgreSQL configuration and readiness | Establishes the secure local connection contract before migrations. |
| `TASK-010` | Module-owned schema persistence and migrations | Persists drafts and immutable publications without domain coupling. |
| `TASK-011` | Tenant-scoped schema repositories | Gives application workflows durable, isolated schema access. |
| `TASK-012` | Durability, immutability, and isolation evidence | Proves the persistence behavior before API and UI consumption. |

Only `TASK-009` is ready. The later passes remain in backlog until their declared predecessor is complete. `TASK-008` belongs to the production deployment story and remains deferred until the product development phase is nearing completion.

The earlier detailed passes under cancelled `STORY-010` through `STORY-016` are retained as cancelled history. Relevant work will be decomposed again in the context of the product story that consumes it.
