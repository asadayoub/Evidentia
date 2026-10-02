"""Tests for provider-neutral runtime health reporting."""

import asyncio

from evidentia.runtime.health import liveness_report, readiness_report


def test_liveness_does_not_depend_on_external_services() -> None:
    report = liveness_report("api")

    assert report.as_dict() == {"service": "api", "status": "alive"}


def test_readiness_aggregates_checks_without_exposing_errors() -> None:
    async def available() -> None:
        return None

    async def unavailable() -> None:
        raise RuntimeError("secret connection detail")

    report = asyncio.run(readiness_report("api", {"database": available, "storage": unavailable}))

    assert report.as_dict() == {
        "dependencies": {"database": "ready", "storage": "not_ready"},
        "service": "api",
        "status": "not_ready",
    }
    assert "secret connection detail" not in str(report.as_dict())
