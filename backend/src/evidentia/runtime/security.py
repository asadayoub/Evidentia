"""Structured security-event emission without secret-bearing payloads.

@skyhook-implements NFR-006
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Final

from evidentia.config.settings import RuntimeEnvironment

_EVENT_NAME: Final = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


def emit_security_event(
    event: str,
    *,
    service: str,
    environment: RuntimeEnvironment,
    version: str,
    correlation_id: str | None = None,
    attributes: Mapping[str, object] | None = None,
) -> None:
    """Emit one stable event with runtime and attribution metadata.

    Callers provide identifiers and reason codes only. The shared JSON formatter
    still redacts any attribute whose key indicates password, token, secret,
    credential, or authorization material.

    @skyhook-implements NFR-006
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    if _EVENT_NAME.fullmatch(event) is None:
        raise ValueError("security event names must be lowercase dotted machine names")
    logging.getLogger(f"evidentia.{service}.security").info(
        "security_event",
        extra={
            "service": service,
            "environment": environment.value,
            "version": version,
            "correlation_id": correlation_id,
            "security_event": event,
            **dict(attributes or {}),
        },
    )
