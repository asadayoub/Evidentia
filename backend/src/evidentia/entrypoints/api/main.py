"""FastAPI composition root with explicit runtime configuration and health.

@skyhook-implements REQ-012
@skyhook-implements NFR-006
@skyhook-story STORY-007
@skyhook-story STORY-009
"""

import argparse
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from evidentia.config.settings import ApiSettings, load_api_settings
from evidentia.entrypoints.api.access import AccessApiRuntime, create_access_router
from evidentia.entrypoints.api.documents import DocumentApiRuntime, create_document_router
from evidentia.entrypoints.api.errors import ApiError, ErrorResponse
from evidentia.entrypoints.api.schemas import SchemaApiRuntime, create_schema_router
from evidentia.entrypoints.api.security import CORRELATION_HEADER_NAME, correlation_id
from evidentia.runtime import (
    configure_service_logging,
    emit_security_event,
    liveness_report,
    readiness_report,
)

APP_TITLE: Final = "Evidentia API"
_ReadinessCheck = Callable[[], Awaitable[None]]
_LOGGER = logging.getLogger(__name__)


def create_app(
    settings: ApiSettings | None = None,
    readiness_checks: Mapping[str, _ReadinessCheck] | None = None,
    *,
    access_runtime: AccessApiRuntime | None = None,
    schema_runtime: SchemaApiRuntime | None = None,
    document_runtime: DocumentApiRuntime | None = None,
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
    resolved_access_runtime = access_runtime or AccessApiRuntime(resolved_settings)
    resolved_schema_runtime = schema_runtime or SchemaApiRuntime(resolved_settings)
    resolved_document_runtime = document_runtime or DocumentApiRuntime(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await resolved_access_runtime.close()
        await resolved_schema_runtime.close()
        await resolved_document_runtime.close()

    application = FastAPI(
        title=APP_TITLE,
        version=resolved_settings.version,
        description="Governed Evidentia API",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.access_runtime = resolved_access_runtime
    application.state.schema_runtime = resolved_schema_runtime
    application.state.document_runtime = resolved_document_runtime
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.api.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Idempotency-Key",
            "X-Correlation-ID",
            "X-CSRF-Token",
        ],
        expose_headers=["X-Correlation-ID"],
    )

    @application.middleware("http")
    async def _browser_security(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.correlation_id = correlation_id(request)
        origin = request.headers.get("origin")
        request_origin = str(request.base_url).rstrip("/")
        response: Response
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin is not None
            and origin not in {*resolved_settings.api.allowed_origins, request_origin}
        ):
            emit_security_event(
                "access.origin.denied",
                service="api",
                environment=resolved_settings.environment,
                version=resolved_settings.version,
                correlation_id=request.state.correlation_id,
                attributes={"outcome": "denied", "origin": origin},
            )
            response = JSONResponse(
                status_code=403,
                content=ErrorResponse(
                    error="The request origin is not trusted.",
                    code="origin_rejected",
                ).model_dump(),
            )
        else:
            try:
                response = await call_next(request)
            except Exception as error:
                _LOGGER.exception("unhandled API request failure", exc_info=error)
                response = JSONResponse(
                    status_code=500,
                    content=ErrorResponse(
                        error="The service could not complete the request.",
                        code="internal_error",
                    ).model_dump(),
                )
        response.headers[CORRELATION_HEADER_NAME] = request.state.correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith(("/api/v1/access", "/api/v1/schemas", "/api/v1/documents")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(ApiError)
    async def _api_error(_: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=ErrorResponse(error=error.error, code=error.code).model_dump(),
            headers=error.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error="The request payload is invalid.",
                code="invalid_request",
            ).model_dump(),
        )

    @application.exception_handler(Exception)
    async def _unexpected_error(_: Request, error: Exception) -> JSONResponse:
        _LOGGER.exception("unhandled API request failure", exc_info=error)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="The service could not complete the request.",
                code="internal_error",
            ).model_dump(),
        )

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

    application.include_router(create_access_router(resolved_access_runtime))
    application.include_router(
        create_schema_router(resolved_schema_runtime, resolved_access_runtime)
    )
    application.include_router(
        create_document_router(resolved_document_runtime, resolved_access_runtime)
    )

    def _openapi() -> dict[str, object]:
        if application.openapi_schema is None:
            schema = get_openapi(
                title=application.title,
                version=application.version,
                description=application.description,
                routes=application.routes,
                openapi_version=application.openapi_version,
            )
            components = schema.setdefault("components", {})
            security_schemes = components.setdefault("securitySchemes", {})
            security_schemes["sessionCookie"] = {
                "type": "apiKey",
                "in": "cookie",
                "name": resolved_settings.session.cookie_name,
                "description": "Opaque revocable browser session; never expose it to JavaScript.",
            }
            for path_item in schema["paths"].values():
                for operation in path_item.values():
                    if isinstance(operation, dict):
                        operation.get("responses", {}).pop("422", None)
            schemas = components.get("schemas", {})
            schemas.pop("HTTPValidationError", None)
            schemas.pop("ValidationError", None)
            application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = _openapi  # type: ignore[method-assign]

    return application


app = create_app()


def main(argv: Sequence[str] | None = None) -> None:
    """Run the API server from validated runtime settings.

    @skyhook-implements REQ-012
    @skyhook-implements NFR-004
    @skyhook-implements NFR-006
    @skyhook-story STORY-007
    @skyhook-story STORY-009
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    parser = argparse.ArgumentParser(prog="evidentia-api")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="optional validated environment file",
    )
    arguments = parser.parse_args(argv)
    settings = load_api_settings(arguments.env_file)
    logger = configure_service_logging(
        settings.logging,
        service=settings.service,
        environment=settings.environment,
        version=settings.version,
    )
    logger.info("starting API service")
    uvicorn.run(
        create_app(settings),
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.reload,
    )
