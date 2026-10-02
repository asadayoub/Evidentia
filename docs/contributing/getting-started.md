# Contributor setup

## Prerequisites

Install Git, nvm, uv, and the container runtime selected for your platform. Evidentia pins the Node and Python patch versions used to create its lockfiles while supporting their accepted runtime lines.

## Reproduce the workspace

```sh
nvm install
nvm use
corepack enable
corepack install
make bootstrap
make check
```

`make bootstrap` uses frozen installs. When intentionally changing a Python dependency, update its manifest and run `uv lock`; when intentionally changing a TypeScript dependency, update its manifest through pnpm and commit the resulting `pnpm-lock.yaml` change.

Do not edit generated files manually. The OpenAPI and SDK generation workflow will be introduced by `STORY-012`; until then, `make generated-check` verifies lockfile integrity and any generated metadata already present.

## Run Evidentia locally

After installing Docker with the Compose plugin, generate local credentials and start the supported composition:

```sh
make local-init
make local-up
```

Use `make local-verify` for a repeatable health check and `make local-down` to stop containers without deleting data. The complete security, reset, and troubleshooting guidance is in [`../operations/local-runtime.md`](../operations/local-runtime.md).

## Runtime policy

The repository currently targets Python 3.14.x, Node.js 24 LTS, and PostgreSQL 18.x. Runtime-line changes require the architecture review and compatibility validation described in `docs/architecture/development-toolchain.md`.
