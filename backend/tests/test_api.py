"""Tests for the API bootstrap composition root."""

from evidentia.entrypoints.api import create_app


def test_create_app_exposes_liveness_operation() -> None:
    app = create_app()

    operation_ids = {route.operation_id for route in app.routes if hasattr(route, "operation_id")}

    assert app.title == "Evidentia API"
    assert "platform_liveness" in operation_ids
