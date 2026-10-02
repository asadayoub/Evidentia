# Evidentia Development Toolchain

Status: Accepted  
Skyhook story: `STORY-006`

## Decision summary

Evidentia uses a reproducible, contract-first toolchain for a Python 3.14 backend and a Node.js 24 LTS frontend/tooling environment. Python dependencies are managed by `uv`; JavaScript and TypeScript dependencies are managed by `pnpm`. Exact transitive dependency and tool versions are committed in lockfiles, while this document fixes the supported runtime lines and engineering rules rather than copying a quickly stale list of package patch versions.

The selected baseline is:

| Area                                 | Selection                                                                                   |
| ------------------------------------ | ------------------------------------------------------------------------------------------- |
| Backend runtime                      | Python 3.14.x                                                                               |
| Frontend/tooling runtime             | Node.js 24 LTS                                                                              |
| Database                             | PostgreSQL 18, kept on the current supported minor                                          |
| Python package/workspace manager     | `uv`, with one committed root `uv.lock`                                                     |
| TypeScript package/workspace manager | `pnpm`, with one committed root `pnpm-lock.yaml`                                            |
| HTTP API                             | FastAPI and Pydantic 2, emitting OpenAPI 3.1                                                |
| Persistence                          | SQLAlchemy 2 async, psycopg 3, and Alembic                                                  |
| Backend lint/format                  | Ruff                                                                                        |
| Backend static typing                | mypy in strict mode                                                                         |
| Backend tests                        | pytest, pytest-asyncio, and Testcontainers for integration tests                            |
| Architecture enforcement             | Import Linter plus repository-owned architecture tests                                      |
| Frontend build                       | React, TypeScript, and Vite                                                                 |
| Frontend lint/format                 | ESLint flat config, type-aware typescript-eslint, React Hooks rules, jsx-a11y, and Prettier |
| Frontend tests                       | Vitest, React Testing Library, and user-event                                               |
| End-to-end tests                     | Playwright                                                                                  |
| TypeScript API client                | `openapi-typescript` plus `openapi-fetch`                                                   |
| Python API client                    | `openapi-python-client`, wrapped by a small supported SDK surface                           |
| API compatibility                    | Checked OpenAPI artifact plus pinned `oasdiff` breaking-change checks                       |
| Local services                       | Docker Compose                                                                              |

The worker execution framework, realtime transport, hosted CI provider, production orchestrator, and cloud providers remain replaceable decisions. Their validation commands must plug into the same provider-neutral CI interface.

## Version and lock policy

- Runtime lines are pinned in repository configuration and container images: Python `3.14.x`, Node `24.x LTS`, and PostgreSQL `18.x`.
- Developer setup, CI, containers, and release builds consume the same lockfiles.
- `uv.lock` and `pnpm-lock.yaml` are committed. CI installs in locked/frozen mode and fails if a manifest would change a lockfile.
- Direct dependencies use intentional compatible constraints in their manifests; resolved direct and transitive versions remain exact in lockfiles.
- Standalone CI tools and container images are pinned to an exact version or immutable digest. Floating `latest` tags are prohibited in reproducible jobs.
- Renovation is deliberate: automated update proposals may refresh locks, but tests, generated-artifact checks, contract compatibility, and release notes must pass before merge.
- Patch updates may be grouped. Minor and major updates are reviewed separately when they alter contracts, persistence, security behavior, generated output, or deployment behavior.
- Supported PostgreSQL minors and security updates are applied promptly without changing the logical database contract.

Python 3.15 is not selected while it is in prerelease. Node 26 is not selected while it is the Current line rather than LTS. The project moves runtime lines through an ADR after dependency, container, migration, and compatibility validation.

## Python workspace and backend rules

The repository root owns the `uv` workspace and lockfile. The backend application and Python SDK may be separate workspace members, so they can be packaged independently while sharing resolution and development commands.

- Application packages use a `src/` layout and are importable only through declared package surfaces.
- FastAPI entrypoints perform HTTP concerns and dependency wiring; domain modules do not import FastAPI, SQLAlchemy, or infrastructure adapters.
- Pydantic models at HTTP and integration boundaries are distinct from SQLAlchemy persistence models and domain entities.
- SQLAlchemy uses the 2.x typed API and async sessions. Sessions and transactions are passed through application ports; modules do not create hidden global sessions.
- psycopg 3 is the PostgreSQL driver. Production code does not use an in-memory substitute as proof of PostgreSQL behavior.
- Alembic has module-owned version locations or bases. A migration may coordinate an explicitly reviewed cross-module rollout, but tables and routine migrations retain one module owner.
- Ruff is the single formatter and primary linter. It replaces overlapping Black, isort, and Flake8-style jobs unless a documented gap requires a dedicated tool.
- mypy runs in strict mode for production packages. Any narrowly scoped exception includes a reason and removal condition.
- pytest marks unit, integration, contract, end-to-end, performance, and slow tests explicitly. Async behavior is tested with pytest-asyncio.
- PostgreSQL and other infrastructure integration tests use disposable containers through Testcontainers. Unit tests may use fakes at declared ports but do not masquerade SQLite behavior as PostgreSQL validation.
- Import Linter and repository-owned AST/import tests enforce domain purity, permitted module public surfaces, dependency direction, and the prohibition on cross-module persistence access.

`ty` can be evaluated later as a fast secondary checker, but it is not the required gate while its own project labels it beta. Replacing mypy requires a compatibility run over the whole typed codebase and an ADR.

## TypeScript workspace and frontend rules

The root `pnpm-workspace.yaml` contains the frontend and TypeScript SDK packages. Workspace dependency cycles are rejected, and internal packages use explicit workspace dependencies.

- TypeScript enables `strict`, `noUncheckedIndexedAccess`, and consistent indexed/optional-property handling appropriate to generated OpenAPI types.
- ESLint uses flat configuration with type-aware typescript-eslint rules, React Hooks rules, and jsx-a11y checks.
- Prettier owns presentation formatting; ESLint owns correctness and architectural rules. Their configurations must not duplicate or fight each other.
- Vitest handles unit tests and React Testing Library plus user-event handles component behavior from the user's perspective.
- Playwright validates critical browser journeys, authorization boundaries, uploads/downloads, and cross-browser behavior. Accessibility assertions are included in relevant journeys; static lint alone is not treated as accessibility proof.
- Frontend feature code consumes the generated/supported API client. It does not duplicate backend DTOs by hand or make undocumented HTTP calls.

## API contract and SDK workflow

FastAPI's generated OpenAPI 3.1 document is the implementation-derived source for the public HTTP contract, but a normalized artifact under `contracts/openapi/` is committed and reviewed.

The workflow is:

1. Build the application deterministically without contacting external services.
2. Export and normalize OpenAPI from the composed FastAPI app.
3. Validate the specification and compare it with the checked artifact.
4. Run `oasdiff` against the merge-base contract; unapproved breaking changes fail CI.
5. Regenerate TypeScript and Python clients using exactly pinned generators.
6. Fail CI if regeneration changes committed generated files.
7. Run SDK type checks, builds, unit tests, and contract/conformance tests.
8. Require explicit deprecation, versioning, migration guidance, and release notes for intentionally accepted breaking changes.

Every public operation has a stable, unique, human-readable `operationId`, a bounded-context tag, documented authorization behavior, idempotency semantics where relevant, and defined error responses. SDK generators consume only the checked public contract, never backend persistence models.

Generated code is isolated from handwritten ergonomic wrappers. Generator changes are reviewed like contract changes because they can alter the supported SDK surface even when the OpenAPI document does not change.

## CI contract

CI-provider configuration is a thin caller of scripts under `ci/` or declared package commands. A developer can run the same checks locally. The required gates are:

1. lockfile integrity and reproducible installation;
2. generated-file cleanliness;
3. formatting checks;
4. linting and static typing;
5. Skyhook policy, standards, and traceability checks;
6. architecture and dependency-boundary tests;
7. backend and frontend unit/component tests;
8. OpenAPI validation and breaking-change detection;
9. SDK generation, build, and conformance tests;
10. PostgreSQL and adapter integration tests;
11. Playwright end-to-end tests for selected critical journeys;
12. dependency, secret, and container vulnerability scans;
13. production container builds and startup/health smoke tests.

Fast pull-request jobs may shard or defer expensive suites, but protected-branch merge policy must eventually require the full risk-appropriate set. Performance, recovery, migration rehearsal, and broad evaluation suites may run on a scheduled or release cadence when their runtime is unsuitable for every pull request.

## Upgrade policy

- Dependency updates are automated as proposals, never silently merged.
- A monthly maintenance window handles ordinary dependency refreshes; critical security fixes bypass that cadence.
- Runtime, database-major, ORM-major, API-generator, or formatter changes require focused release notes and may require an ADR when they alter architectural behavior or checked output.
- Database-major upgrades require backup/restore rehearsal, migration validation, rollback or forward-recovery guidance, and representative performance checks.
- Formatter or generator upgrades occur in isolated changes to keep mechanical diffs separate from feature work.
- End-of-life dates are monitored. The project begins runtime-line migration early enough to support both old and new lines during validation when practical.

## Deferred choices and extension points

These remain intentionally open until their capability is scheduled:

- worker/job engine and delivery guarantees;
- realtime transport (WebSocket, SSE, Firebase, or another adapter);
- CI hosting provider;
- production container orchestration and cloud hosting;
- observability backend;
- OCR, extraction, inference, email, and external-approval providers.

Each is selected behind an existing port or provider-neutral command surface. A deferred choice may not weaken the locked dependency workflow, module boundaries, contract checks, tenant isolation, auditability, or local Docker Compose development path.

## Primary references

- [Python version status](https://devguide.python.org/versions/)
- [Node.js release lines](https://nodejs.org/en/about/previous-releases)
- [PostgreSQL versioning policy](https://www.postgresql.org/support/versioning/)
- [uv workspaces](https://docs.astral.sh/uv/concepts/workspaces/)
- [pnpm workspaces](https://pnpm.io/workspaces)
- [FastAPI SDK generation and OpenAPI 3.1](https://fastapi.tiangolo.com/advanced/generate-clients/)
- [SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Alembic multiple bases](https://alembic.sqlalchemy.org/en/latest/branches.html)
- [Ruff](https://docs.astral.sh/ruff/)
- [mypy](https://mypy.readthedocs.io/en/stable/)
- [TypeScript strict mode](https://www.typescriptlang.org/tsconfig/strict)
- [typescript-eslint typed linting](https://typescript-eslint.io/getting-started/typed-linting/)
- [Testcontainers for Python](https://testcontainers.com/guides/getting-started-with-testcontainers-for-python/)
- [oasdiff breaking-change checks](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-CHANGES.md)
- [OpenAPI TypeScript](https://openapi-ts.dev/introduction)
- [Playwright](https://playwright.dev/docs/intro)
