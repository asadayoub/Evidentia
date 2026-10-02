# Runtime configuration

Status: Initial contract implemented by `STORY-009`, pass `009.1`  
Governing decision: `8VC3FRAN1GRTK2F99NB459BWWJ`

## Purpose

Evidentia loads configuration through `pydantic-settings` at API and worker composition roots. Settings are immutable after validation and are passed explicitly to dependencies. Modules must not read environment variables or import a global settings singleton.

## Profiles

- `development` permits safe local defaults and generated local credentials.
- `test` permits isolated test values and deterministic overrides.
- `production` fails startup when required secrets are absent, blank, or recognized placeholders. API reload behavior is also forbidden.

The profile is selected with `EVIDENTIA_ENVIRONMENT`.

## Environment structure

Nested settings use a double underscore:

```text
EVIDENTIA_ENVIRONMENT=development
EVIDENTIA_DATABASE__HOST=postgres
EVIDENTIA_DATABASE__PORT=5432
EVIDENTIA_DATABASE__NAME=evidentia
EVIDENTIA_DATABASE__USER=evidentia
EVIDENTIA_DATABASE__PASSWORD=<generated-local-value>
EVIDENTIA_LOGGING__LEVEL=INFO
EVIDENTIA_LOGGING__JSON=false
EVIDENTIA_STORAGE__BACKEND=filesystem
EVIDENTIA_STORAGE__ROOT=/var/lib/evidentia/artifacts
EVIDENTIA_API__HOST=0.0.0.0
EVIDENTIA_API__PORT=8000
EVIDENTIA_API__RELOAD=false
EVIDENTIA_WORKER__SHUTDOWN_GRACE_SECONDS=30
```

This naming contract is represented by the deliberately unusable `.env.example`. The supported `make local-init` workflow generates a private `.env` with a random local database password and refuses to replace an existing environment.

## Service ownership

`ApiSettings` and `WorkerSettings` share database, logging, storage, environment, and version conventions. API binding/reload values and worker lifecycle values remain service-specific. Loading functions return fresh instances so tests and multiple process compositions cannot mutate shared global state.

Secret values use Pydantic secret types and remain redacted in representations and serialized diagnostic output. Code that actually opens a database connection must unwrap the secret only at that adapter boundary.

## Runtime observability

API and worker composition roots share provider-neutral logging and health primitives from `evidentia.runtime`:

- structured logs always carry service, environment, version, and correlation identifiers;
- JSON logs defensively redact fields whose names indicate credentials or secrets;
- liveness reports only that the process is running and never calls dependencies;
- readiness runs the dependency checks supplied by the composition root and returns only `ready` or `not_ready` for each dependency, without exception text or connection details.

No dependency registry is global. Later database, storage, and queue adapters will supply their checks when each process is assembled. This keeps readiness extensible without coupling runtime infrastructure to a provider or bounded context.
