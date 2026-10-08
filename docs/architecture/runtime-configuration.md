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
EVIDENTIA_DATABASE__HOST=127.0.0.1
EVIDENTIA_DATABASE__PORT=5432
EVIDENTIA_DATABASE__NAME=evidentia
EVIDENTIA_DATABASE__USER=evidentia
EVIDENTIA_DATABASE__PASSWORD=<generated-local-value>
EVIDENTIA_DATABASE__CONNECT_TIMEOUT_SECONDS=5
EVIDENTIA_DATABASE__SSLMODE=prefer
EVIDENTIA_DATABASE__APPLICATION_NAME=evidentia
EVIDENTIA_LOGGING__LEVEL=INFO
EVIDENTIA_LOGGING__JSON=false
EVIDENTIA_STORAGE__BACKEND=filesystem
EVIDENTIA_STORAGE__ROOT=/var/lib/evidentia/artifacts
EVIDENTIA_STORAGE__MAXIMUM_UPLOAD_BYTES=26214400
EVIDENTIA_IDENTITY__BOOTSTRAP_LOGIN_IDENTIFIER=admin@localhost
EVIDENTIA_IDENTITY__BOOTSTRAP_TENANT_SLUG=local
EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD=<generated-local-value>
EVIDENTIA_SESSION__SECRET=<generated-local-value>
EVIDENTIA_SESSION__IDLE_TIMEOUT_SECONDS=1800
EVIDENTIA_SESSION__ABSOLUTE_TIMEOUT_SECONDS=43200
EVIDENTIA_SESSION__COOKIE_NAME=evidentia_session
EVIDENTIA_SESSION__COOKIE_SECURE=false
EVIDENTIA_SESSION__COOKIE_SAMESITE=lax
EVIDENTIA_API__HOST=0.0.0.0
EVIDENTIA_API__PORT=8000
EVIDENTIA_API__RELOAD=false
EVIDENTIA_WORKER__SHUTDOWN_GRACE_SECONDS=30
```

The local artifact directory stores originals outside PostgreSQL. Restrict its
filesystem permissions and include it in deployment backup and restore plans.
The default upload limit is 25 MiB and can be adjusted with
`EVIDENTIA_STORAGE__MAXIMUM_UPLOAD_BYTES`.

This naming contract is represented by the deliberately unusable `.env.example`. The supported `make local-init` workflow generates a private `.env` with separate random database, bootstrap, and session secrets and refuses to replace an existing environment. `make local-env-upgrade` atomically adds missing settings to an older file without replacing any existing value.

The current development workflow uses native PostgreSQL 16.x. `make native-db-init` creates or aligns the dedicated local role and database without running migrations, and `make native-db-verify` performs a read-only authenticated version/database/role check. Docker remains optional until the deferred hybrid profile is implemented.

## Service ownership

`ApiSettings` and `WorkerSettings` share database, logging, storage, identity, opaque-session, environment, and version conventions. API binding/reload values and worker lifecycle values remain service-specific. Loading functions return fresh instances so tests and multiple process compositions cannot mutate shared global state.

Secret values use Pydantic secret types and remain redacted in representations and serialized diagnostic output. Code that actually opens a database connection must unwrap the secret only at that adapter boundary.

Bootstrap credentials configure an explicit provisioning command; they do not cause account creation during service startup. Production requires a non-placeholder session secret and secure cookies. Provider-specific identity configuration will remain behind the Access context's public provider port so future OIDC adoption does not change downstream tenant-context contracts.

## Runtime observability

API and worker composition roots share provider-neutral logging and health primitives from `evidentia.runtime`:

- structured logs always carry service, environment, version, and correlation identifiers;
- JSON logs defensively redact fields whose names indicate credentials or secrets;
- liveness reports only that the process is running and never calls dependencies;
- readiness runs the dependency checks supplied by the composition root and returns only `ready` or `not_ready` for each dependency, without exception text or connection details.

No dependency registry is global. Later database, storage, and queue adapters will supply their checks when each process is assembled. This keeps readiness extensible without coupling runtime infrastructure to a provider or bounded context.
