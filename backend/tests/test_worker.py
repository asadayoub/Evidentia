"""Tests for the worker bootstrap composition root."""

import asyncio

from evidentia.entrypoints.worker import worker_probe, worker_readiness


def test_worker_probe_is_explicitly_bootstrap_only() -> None:
    assert worker_probe() == {
        "mode": "bootstrap",
        "service": "worker",
        "status": "ok",
    }


def test_worker_readiness_uses_shared_dependency_contract() -> None:
    async def available_database() -> None:
        return None

    report = asyncio.run(worker_readiness({"database": available_database}))

    assert report == {
        "dependencies": {"database": "ready"},
        "service": "worker",
        "status": "ready",
    }
