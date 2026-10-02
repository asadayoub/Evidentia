"""Tests for structured runtime logging and defensive redaction."""

import io
import json
from typing import Any

from evidentia.config.settings import LoggingSettings, RuntimeEnvironment
from evidentia.runtime.logging import configure_service_logging


def test_json_logging_adds_runtime_context_and_redacts_sensitive_extras() -> None:
    stream = io.StringIO()
    logger = configure_service_logging(
        LoggingSettings(json=True),
        service="api",
        environment=RuntimeEnvironment.TEST,
        version="1.2.3",
        stream=stream,
    )

    logger.info(
        "request accepted",
        extra={
            "correlation_id": "request-123",
            "database_password": "never-log-this",
            "request": {"authorization": "Bearer private", "method": "POST"},
        },
    )
    payload: dict[str, Any] = json.loads(stream.getvalue())

    assert payload["message"] == "request accepted"
    assert payload["service"] == "api"
    assert payload["environment"] == "test"
    assert payload["version"] == "1.2.3"
    assert payload["correlation_id"] == "request-123"
    assert payload["database_password"] == "[REDACTED]"
    assert payload["request"] == {"authorization": "[REDACTED]", "method": "POST"}
    assert "never-log-this" not in stream.getvalue()
