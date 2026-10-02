.PHONY: bootstrap format format-check lint architecture-check type-check unit-test generated-check check

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

generated-check:
	./ci/generated-check.sh

check:
	./ci/check.sh
