# Evidentia

Evidentia turns documents into trustworthy, schema-driven records whose source evidence, corrections, validation, authorization, and delivery history can be inspected and reproduced.

This repository contains the Evidentia backend API and worker, React web application, public contracts, supported SDKs, tests, infrastructure assets, and governed project intelligence. Delibera remains a separate optional integration.

## Supported development runtimes

- Python 3.14.x (`.python-version` currently selects 3.14.4)
- Node.js 24 LTS (`.nvmrc` currently selects 24.21.0)
- pnpm 12.8.1 through Corepack
- uv 0.12.21 or a compatible newer 0.x release capable of consuming the committed lockfile
- PostgreSQL 18.x for persistence work (introduced by the local-runtime story)

## Bootstrap

Install [uv](https://docs.astral.sh/uv/) and [nvm](https://github.com/nvm-sh/nvm), then run:

```sh
nvm install
nvm use
corepack enable
corepack install
make bootstrap
```

The bootstrap command performs frozen installs from `uv.lock` and `pnpm-lock.yaml`. It does not silently update dependency resolution.

## Quality commands

```sh
make format-check
make lint
make type-check
make unit-test
make generated-check
make check
```

These commands are provider-neutral and are the interface a future hosted CI configuration will call.

## Local runtime

With Docker and its Compose plugin installed:

```sh
make local-init
make local-up
```

`local-init` generates an ignored, owner-readable environment with independent random database, identity-bootstrap, and session secrets. Existing environments can add newly required keys without replacing values through `make local-env-upgrade`. `local-up` builds the supported PostgreSQL, API, worker, and web composition and verifies readiness. See [`docs/operations/local-runtime.md`](docs/operations/local-runtime.md) for verification, shutdown, reset, and troubleshooting guidance.

Architecture and governance are documented under [`docs/architecture`](docs/architecture) and `.skyhook/`.
