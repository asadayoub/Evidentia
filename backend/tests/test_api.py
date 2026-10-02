"""Tests for the API composition root and its operational health surface."""

import asyncio
import json
from collections.abc import Callable, Coroutine
from typing import Any, cast

from fastapi.responses import JSONResponse

from evidentia.config.settings import ApiSettings
from evidentia.entrypoints.api import create_app


def test_create_app_exposes_liveness_operation() -> None:
    app = create_app(ApiSettings(version="9.8.7"))

    operation_ids = {route.operation_id for route in app.routes if hasattr(route, "operation_id")}

    assert app.title == "Evidentia API"
    assert app.version == "9.8.7"
    assert "platform_liveness" in operation_ids
    assert "platform_readiness" in operation_ids


def test_api_readiness_returns_service_unavailable_for_a_failed_dependency() -> None:
    async def unavailable_database() -> None:
        raise ConnectionError("private database host must not escape")

    app = create_app(ApiSettings(), {"database": unavailable_database})
    endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "operation_id", None) == "platform_readiness"
    )
    readiness_endpoint = cast(Callable[[], Coroutine[Any, Any, JSONResponse]], endpoint)

    response = asyncio.run(readiness_endpoint())

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "dependencies": {"database": "not_ready"},
        "service": "api",
        "status": "not_ready",
    }
    assert b"private database host" not in response.body
