"""PostgreSQL fixture bridge for authenticated document HTTP tests."""

from backend.tests.integration.conftest import (
    disposable_postgres_database as disposable_postgres_database,
)

__all__ = ("disposable_postgres_database",)
