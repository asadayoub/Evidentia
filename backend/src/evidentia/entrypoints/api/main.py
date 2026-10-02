"""FastAPI composition root with explicit runtime configuration and health.

@skyhook-implements REQ-012
@skyhook-implements NFR-006
@skyhook-story STORY-007
@skyhook-story STORY-009
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import Final

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from evidentia.config.settings import ApiSettings, load_api_settings
from evidentia.runtime import configure_service_logging, liveness_report, readiness_report

APP_TITLE: Final = "Evidentia API"
_ReadinessCheck = Callable[[], Awaitable[None]]


def create_app(
    settings: ApiSettings | None = None,
    readiness_checks: Mapping[str, _ReadinessCheck] | None = None,
) -> FastAPI:
    """Create the API composition root.

    @skyhook-implements REQ-012
    @skyhook-implements NFR-004
    @skyhook-implements NFR-006
    @skyhook-story STORY-007
    @skyhook-story STORY-009
    """
    resolved_settings = settings or load_api_settings()
    resolved_checks = dict(readiness_checks or {})
    application = FastAPI(
        title=APP_TITLE,
        version=resolved_settings.version,
        description="Governed Evidentia API",
    )
    application.state.settings = resolved_settings

    @application.get(
        "/health/live",
        operation_id="platform_liveness",
        tags=["platform"],
        summary="Report API process liveness",
    )
    async def _liveness() -> dict[str, str | dict[str, str]]:
        return liveness_report(resolved_settings.service).as_dict()

    @application.get(
        "/health/ready",
        operation_id="platform_readiness",
        tags=["platform"],
        summary="Report API dependency readiness",
        responses={503: {"description": "One or more dependencies are unavailable"}},
    )
    async def _readiness() -> JSONResponse:
        report = await readiness_report(resolved_settings.service, resolved_checks)
        status_code = 200 if report.status == "ready" else 503
        return JSONResponse(status_code=status_code, content=report.as_dict())

    return application


app = create_app()


def main() -> None:
    """Run the API server from validated runtime settings.

    @skyhook-implements REQ-012
    @skyhook-implements NFR-004
    @skyhook-implements NFR-006
    @skyhook-story STORY-007
    @skyhook-story STORY-009
    """
    settings = load_api_settings()
    logger = configure_service_logging(
        settings.logging,
        service=settings.service,
        environment=settings.environment,
        version=settings.version,
    )
    logger.info("starting API service")
    uvicorn.run(
        "evidentia.entrypoints.api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.reload,
    )
