.PHONY: bootstrap format format-check lint architecture-check type-check unit-test generate-api-contract generated-check container-smoke local-init local-env-upgrade native-db-init native-db-verify native-api db-upgrade db-downgrade identity-init postgres-test local-up local-verify local-down check

UV_CACHE_DIR ?= $(CURDIR)/.uv-cache
export UV_CACHE_DIR

bootstrap:
	./ci/bootstrap.sh

format:
	uv run ruff format .
	uv run ruff check --fix .
	pnpm format

format-check:
	./ci/format-check.sh

lint:
	./ci/lint.sh

architecture-check:
	PYTHONPATH=backend/src uv run lint-imports --no-cache
	uv run python tools/check_architecture.py
	uv run pytest tests/architecture

type-check:
	./ci/type-check.sh

unit-test:
	./ci/unit-test.sh

generate-api-contract:
	uv run python tools/export_openapi.py

generated-check:
	./ci/generated-check.sh

container-smoke:
	./ci/container-smoke.sh

local-init:
	./scripts/generate-local-env.sh

local-env-upgrade:
	./scripts/upgrade-local-env.sh

native-db-verify:
	uv run python tools/check_native_postgres.py

native-db-init:
	uv run python tools/check_native_postgres.py --bootstrap

native-api:
	uv run evidentia-api --env-file .env

db-upgrade:
	uv run alembic -c backend/alembic.ini upgrade heads

db-downgrade:
	uv run alembic -c backend/alembic.ini downgrade base

identity-init:
	uv run evidentia-identity-init --env-file .env

postgres-test:
	uv run pytest --postgres backend/tests/integration backend/tests/api/access

local-up:
	./scripts/local-up.sh

local-verify:
	./ci/local-runtime-check.sh

local-down:
	docker compose --env-file .env -f infra/compose/compose.yaml -f infra/compose/compose.dev.yaml down

check:
	./ci/check.sh
