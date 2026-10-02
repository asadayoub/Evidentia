# Evidentia implementation-pass convention

Skyhook stories remain the governed, leasable delivery units. Each executable story is decomposed into ordered Skyhook `task` records before implementation begins. A task represents one reviewable coding pass with a single primary feature outcome.

## Required task fields

Every implementation pass records:

- **Purpose** in `description`: why the pass exists.
- **Feature** in `metadata.feature`: the concrete capability introduced in this pass.
- **Contribution** in `metadata.contribution`: how that capability advances Evidentia.
- **Scope and evidence** in `technicalNotes`: deliverables and verification expected before the pass is complete.
- **Out of scope** in `metadata.outOfScope`: an explicit guard against accidental expansion.
- **Dependencies** in `dependencies`: earlier passes whose evidence is required first.
- **Estimate and confidence** in `estimate`: a planning aid, not a deadline.

Production symbols introduced by a pass still require the story or requirement traceability annotations mandated by `AGENTS.md`. Story acceptance criteria remain the final completion gate; finishing every child task does not bypass story-level review, policy, standards, drift, traceability, or quality checks.

## Decomposition timing

The complete product remains planned through requirements, epics, stories, dependencies, standards, and ADRs. Detailed implementation passes are added when a story enters the current or next executable wave. This avoids pretending that low-level implementation details are stable before their prerequisite contracts exist.

Before a story moves to `ready`:

1. Confirm its prerequisite stories and accepted ADRs.
2. Add small task records following this convention.
3. Link every task ID from the story's `tasks` field.
4. Make task dependencies acyclic and evidence-based.
5. Mark only immediately executable first passes as `ready`.
6. Recompile the Skyhook plan and verify backlog references.

## Executable platform foundation

| Story | Passes | Delivered sequence |
| --- | ---: | --- |
| STORY-008 | 5 | context map → package skeletons → import contracts → negative/cycle tests → quality integration |
| STORY-009 | 5 | typed settings → logging/health → service containers → Compose infrastructure → secure runbook |
| STORY-010 | 5 | async DB runtime → tenant primitives → migrations → scoped repositories → isolation evidence |
| STORY-011 | 5 | identity contracts → local auth and OIDC → trusted context → authorization/security tests |
| STORY-012 | 5 | API conventions → safe middleware → operation metadata → OpenAPI → generated SDKs |
| STORY-013 | 5 | accessible primitives → routed shell → generated client → tenant UX → conformance tests |
| STORY-014 | 5 | work envelope/port → worker lifecycle → dispatch → test adapter → contract tests |
| STORY-015 | 5 | quality orchestration → layered jobs → supply-chain gates → artifact proof → CI contract |
| STORY-016 | 6 | clean bootstrap → diagnostic API → web slice → worker flow → isolation proof → Gate 0 evidence |

The next executable passes are **008.1 — Declare bounded-context package map** and **009.1 — Implement typed environment configuration**. Story-level leasing remains authoritative; task status documents progress within the leased story.
