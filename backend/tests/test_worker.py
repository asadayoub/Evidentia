"""Tests for the worker bootstrap composition root."""

from evidentia.entrypoints.worker import worker_probe


def test_worker_probe_is_explicitly_bootstrap_only() -> None:
    assert worker_probe() == {
        "mode": "bootstrap",
        "service": "worker",
        "status": "ok",
    }
