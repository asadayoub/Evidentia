"""Tests for structured runtime logging and defensive redaction."""

import io
import json
from typing import Any

from evidentia.config.settings import LoggingSettings, RuntimeEnvironment
from evidentia.runtime.logging import configure_service_logging
from evidentia.runtime.security import emit_security_event


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


def test_security_events_are_structured_and_defensively_redacted() -> None:
    """Keep attribution fields while redacting accidental secret-bearing extras.

    @skyhook-implements NFR-006
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    stream = io.StringIO()
    configure_service_logging(
        LoggingSettings(json=True),
        service="api",
        environment=RuntimeEnvironment.TEST,
        version="1.2.3",
        stream=stream,
    )

    emit_security_event(
        "access.login.succeeded",
        service="api",
        environment=RuntimeEnvironment.TEST,
        version="1.2.3",
        correlation_id="request-456",
        attributes={
            "operator_id": "operator-123",
            "session_token": "must-not-escape",
            "password_hint": "also-private",
        },
    )
    payload: dict[str, Any] = json.loads(stream.getvalue())

    assert payload["security_event"] == "access.login.succeeded"
    assert payload["correlation_id"] == "request-456"
    assert payload["operator_id"] == "operator-123"
    assert payload["session_token"] == "[REDACTED]"
    assert payload["password_hint"] == "[REDACTED]"
    assert "must-not-escape" not in stream.getvalue()
