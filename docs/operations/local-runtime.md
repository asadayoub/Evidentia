# Local runtime operations

Status: Supported by `STORY-009`, pass `009.5`  
Governing decision: `8VC3FRAN1GRTK2F99NB459BWWJ`

## Purpose

The supported local profile runs PostgreSQL 18, the API, worker, and web application through Docker Compose. PostgreSQL data and filesystem-backed artifacts persist in named volumes. This is a local adapter composition, not a production deployment prescription.

## Prerequisites

- Docker with the Compose plugin;
- `make`, `openssl` or Python 3, and `curl`;
- ports 3000, 5432, and 8000 available on loopback, or alternate values in the generated `.env`.

## First start

Generate a private local environment exactly once:

```sh
make local-init
```

This creates `.env` with mode `0600` and a random 256-bit PostgreSQL password. The script refuses to overwrite an existing file. `.env.example` contains only a deliberately unusable marker; do not copy it as a credential source.

Build, start, and wait for all runtime checks with one command:

```sh
make local-up
```

The web application is then available at `http://127.0.0.1:3000` and the API at `http://127.0.0.1:8000`. All published ports bind only to loopback.

## Verify and inspect

Run the same readiness checks independently:

```sh
make local-verify
```

The command validates the merged Compose model, PostgreSQL readiness, the worker probe, API liveness and readiness, and web liveness. For service state or secret-safe structured logs:

```sh
docker compose --env-file .env -f infra/compose/compose.yaml -f infra/compose/compose.dev.yaml ps
docker compose --env-file .env -f infra/compose/compose.yaml -f infra/compose/compose.dev.yaml logs --tail=100
```

## Stop, reset, and recover

Stop containers while retaining both named volumes:

```sh
make local-down
```

To rebuild after dependency or container-definition changes, run `make local-up` again. If a service remains unhealthy, inspect its logs, confirm loopback ports are available, and confirm `.env` was generated rather than copied from the example.

Deleting volumes is intentionally not wrapped in a Make target because it irreversibly removes the local database and stored artifacts. When a complete reset is genuinely intended, first stop the stack and then explicitly run:

```sh
docker compose --env-file .env -f infra/compose/compose.yaml -f infra/compose/compose.dev.yaml down --volumes
```

The local password is not a production secret. External secret management, backup/restore, S3-compatible storage, and production orchestration remain owned by their deferred Skyhook stories and require separate decisions.
