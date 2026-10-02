"""Minimal FastAPI entrypoint used to prove the governed workspace.

@skyhook-implements REQ-012
@skyhook-story STORY-007
"""

from typing import Final

import uvicorn
from fastapi import FastAPI

APP_TITLE: Final = "Evidentia API"


def create_app() -> FastAPI:
    """Create the API composition root.

    @skyhook-implements REQ-012
    @skyhook-story STORY-007
    """
    application = FastAPI(
        title=APP_TITLE,
        version="0.1.0",
        description="Governed Evidentia API foundation",
    )

    @application.get(
        "/health/live",
        operation_id="platform_liveness",
        tags=["platform"],
        summary="Report API process liveness",
    )
    async def _liveness() -> dict[str, str]:
        return {"status": "ok", "service": "api"}

    return application


app = create_app()


def main() -> None:
    """Run the development API server.

    @skyhook-implements REQ-012
    @skyhook-story STORY-007
    """
    uvicorn.run(
        "evidentia.entrypoints.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
