"""Worker composition root with explicit runtime configuration and health.

@skyhook-implements REQ-014
@skyhook-implements NFR-006
@skyhook-story STORY-007
@skyhook-story STORY-009
"""

import signal
import threading
from collections.abc import Awaitable, Callable, Mapping
from types import FrameType

from evidentia.config.settings import load_worker_settings
from evidentia.runtime import configure_service_logging, readiness_report

_ReadinessCheck = Callable[[], Awaitable[None]]


def worker_probe() -> dict[str, str]:
    """Return the worker bootstrap state without starting a job engine.

    @skyhook-implements REQ-014
    @skyhook-story STORY-007
    """
    return {"status": "ok", "service": "worker", "mode": "bootstrap"}


async def worker_readiness(
    readiness_checks: Mapping[str, _ReadinessCheck] | None = None,
) -> dict[str, str | dict[str, str]]:
    """Report whether the worker's configured dependencies are available.

    @skyhook-implements REQ-014
    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """
    report = await readiness_report("worker", readiness_checks or {})
    return report.as_dict()


def main() -> None:
    """Run the worker bootstrap with validated settings and structured logging.

    @skyhook-implements REQ-014
    @skyhook-implements NFR-004
    @skyhook-implements NFR-006
    @skyhook-story STORY-007
    @skyhook-story STORY-009
    """
    settings = load_worker_settings()
    logger = configure_service_logging(
        settings.logging,
        service=settings.service,
        environment=settings.environment,
        version=settings.version,
    )
    stop_requested = threading.Event()

    def _request_stop(_signal_number: int, _frame: FrameType | None) -> None:
        stop_requested.set()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    logger.info("worker bootstrap ready", extra={"mode": "bootstrap"})
    stop_requested.wait()
    logger.info("worker shutdown complete", extra={"mode": "bootstrap"})
