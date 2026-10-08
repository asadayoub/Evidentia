.PHONY: bootstrap format format-check lint architecture-check type-check unit-test generate-api-contract generated-check authenticated-shell-check schema-api-check schema-workbench-check schema-evolution-check container-smoke local-init local-env-upgrade native-db-init native-db-verify native-api native-web db-upgrade db-downgrade identity-init postgres-test local-up local-verify local-down check

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

authenticated-shell-check:
	./ci/authenticated-shell-check.sh

schema-api-check:
	uv run pytest --postgres backend/tests/api/access backend/tests/api/schemas backend/tests/integration/schemas

schema-workbench-check: schema-api-check
	pnpm --filter @evidentia/web test
	pnpm --filter @evidentia/web build

schema-evolution-check: schema-api-check
	uv run pytest backend/tests/modules/schemas/test_schema_evolution.py backend/tests/modules/schemas/test_schema_interchange.py backend/tests/modules/schemas/test_schema_compatibility.py
	./ci/generated-check.sh
	pnpm --filter @evidentia/typescript-sdk test
	pnpm --filter @evidentia/web test
	pnpm --filter @evidentia/web build

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

native-web:
	pnpm --filter @evidentia/web dev

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
