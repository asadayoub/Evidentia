"""Dependency-aware health reporting shared by service composition roots.

@skyhook-implements NFR-006
@skyhook-story STORY-009
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

_ReadinessCheck = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Serializable service health without sensitive diagnostic details.

    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """

    status: Literal["alive", "ready", "not_ready"]
    service: str
    dependencies: dict[str, Literal["ready", "not_ready"]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, str | dict[str, str]]:
        """Return an HTTP- and log-safe representation of this report.

        @skyhook-implements NFR-006
        @skyhook-story STORY-009
        """
        payload: dict[str, str | dict[str, str]] = {
            "status": self.status,
            "service": self.service,
        }
        if self.dependencies:
            payload["dependencies"] = dict(self.dependencies)
        return payload


def liveness_report(service: str) -> HealthReport:
    """Report that the service process is running without probing dependencies.

    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """
    return HealthReport(status="alive", service=service)


async def readiness_report(
    service: str,
    checks: Mapping[str, _ReadinessCheck],
) -> HealthReport:
    """Run dependency checks and return a detail-safe aggregate readiness report.

    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """
    dependencies: dict[str, Literal["ready", "not_ready"]] = {}
    for name, check in checks.items():
        try:
            await check()
        except Exception:
            dependencies[name] = "not_ready"
        else:
            dependencies[name] = "ready"

    status: Literal["ready", "not_ready"] = (
        "ready" if all(value == "ready" for value in dependencies.values()) else "not_ready"
    )
    return HealthReport(status=status, service=service, dependencies=dependencies)
