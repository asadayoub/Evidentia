"""Structured, secret-conscious logging for Evidentia services.

@skyhook-implements NFR-006
@skyhook-story STORY-009
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TextIO

from evidentia.config.settings import LoggingSettings, RuntimeEnvironment

_SENSITIVE_KEY_PARTS = ("authorization", "credential", "password", "secret", "token")
_STANDARD_LOG_RECORD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def _redact(key: str, value: Any) -> Any:
    if any(part in key.lower() for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(child_key): _redact(str(child_key), child) for child_key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(key, item) for item in value]
    if value is None or isinstance(value, (bool, float, int, str)):
        return value
    return str(value)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", "unknown"),
            "environment": getattr(record, "environment", "unknown"),
            "version": getattr(record, "version", "unknown"),
            "correlation_id": getattr(record, "correlation_id", None),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_FIELDS and key not in payload:
                payload[key] = _redact(key, value)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_service_logging(
    settings: LoggingSettings,
    *,
    service: str,
    environment: RuntimeEnvironment,
    version: str,
    stream: TextIO | None = None,
) -> logging.LoggerAdapter[logging.Logger]:
    """Configure and return a service logger carrying stable runtime metadata.

    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """
    logger = logging.getLogger(f"evidentia.{service}")
    logger.handlers.clear()
    logger.setLevel(settings.level)
    logger.propagate = False

    handler = logging.StreamHandler(stream)
    if settings.json_output:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s "
                "service=%(service)s environment=%(environment)s version=%(version)s "
                "correlation_id=%(correlation_id)s %(message)s"
            )
        )
    logger.addHandler(handler)
    return logging.LoggerAdapter(
        logger,
        {
            "service": service,
            "environment": environment.value,
            "version": version,
            "correlation_id": None,
        },
        merge_extra=True,
    )
