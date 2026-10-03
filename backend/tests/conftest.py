"""Shared pytest controls for explicitly enabled integration resources.

@skyhook-implements NFR-004
@skyhook-implements NFR-008
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register explicit permission to use the configured PostgreSQL database.

    @skyhook-implements NFR-004
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    parser.addoption(
        "--postgres",
        action="store_true",
        default=False,
        help="run tests that use the configured native PostgreSQL database",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip PostgreSQL tests unless the developer selected them explicitly.

    @skyhook-implements NFR-004
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    if config.getoption("--postgres"):
        return
    skip = pytest.mark.skip(reason="pass --postgres to use the configured integration database")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip)
