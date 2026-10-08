"""Versioned HTTP adapter for the governed schema lifecycle.

@skyhook-implements REQ-003
@skyhook-implements REQ-012
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements NFR-008
@skyhook-story X51S43NTMRW5ASYSKJBF7FW845
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from evidentia.config.settings import ApiSettings
from evidentia.entrypoints.api.access import AccessApiRuntime
from evidentia.entrypoints.api.errors import ApiError, ErrorResponse
from evidentia.entrypoints.api.security import CSRF_HEADER_NAME, require_csrf, session_token
from evidentia.modules.access.public import (
    AccessDenialReason,
    AccessDeniedError,
    ResolveTrustedContext,
)
from evidentia.modules.schemas.application.idempotency import (
    IdempotencyKeyReuseError,
    SchemaCommandReceipt,
)
from evidentia.modules.schemas.application.repositories import (
    DraftNotFoundError,
    DraftRevisionConflictError,
    PublicationAlreadyExistsError,
    StoredSchemaDraft,
    StoredSchemaPublication,
)
from evidentia.modules.schemas.infrastructure.database import (
    create_schema_engine,
    create_schema_session_factory,
)
from evidentia.modules.schemas.infrastructure.idempotency import PostgresSchemaCommandReceipts
from evidentia.modules.schemas.infrastructure.repository import PostgresSchemaRepository
from evidentia.modules.schemas.public import (
    ArtifactKey,
    ManageSchemaLifecycle,
    SchemaArtifactCatalog,
    SchemaAuthorizationError,
    SchemaCommandContext,
    SchemaDraft,
    SchemaDraftContent,
    SchemaId,
    SchemaVersion,
    export_schema,
    export_schema_draft_content,
    import_schema_draft_content,
)
from evidentia.runtime import emit_security_event

IDEMPOTENCY_HEADER_NAME = "Idempotency-Key"
_SESSION_SECURITY: dict[str, Any] = {"security": [{"sessionCookie": []}]}
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Invalid request"},
    401: {"model": ErrorResponse, "description": "Authentication failed or expired"},
    403: {"model": ErrorResponse, "description": "Request is not authorized"},
    404: {"model": ErrorResponse, "description": "Schema resource was not found"},
    409: {"model": ErrorResponse, "description": "Command conflicts with current state"},
}


class SchemaDraftContentRequest(BaseModel):
    """Dynamic canonical content whose shape is governed by the domain parser.

    @skyhook-implements REQ-003
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    release_label: str | None = Field(default=None, alias="releaseLabel", max_length=64)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    modules: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


class CreateSchemaDraftRequest(BaseModel):
    """Create command containing only client-owned mutable content.

    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    model_config = ConfigDict(extra="forbid")
    content: SchemaDraftContentRequest


class ReplaceSchemaDraftRequest(BaseModel):
    """Revision-guarded full replacement command.

    @skyhook-implements NFR-001
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    content: SchemaDraftContentRequest


class PublishSchemaDraftRequest(BaseModel):
    """Revision-guarded publication command with optional breaking-change acknowledgement.

    @skyhook-implements NFR-001
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    acknowledgement: str | None = Field(default=None, min_length=1, max_length=2000)


class SchemaDraftResponse(BaseModel):
    """Mutable schema snapshot with concurrency and audit metadata.

    @skyhook-implements REQ-003
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_id: str
    version: int
    revision: int
    content: dict[str, Any]
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class SchemaDraftPageResponse(BaseModel):
    """Stable cursor page of tenant-visible schema drafts.

    @skyhook-implements REQ-003
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    items: tuple[SchemaDraftResponse, ...]
    next_cursor: str | None


class SchemaPublicationResponse(BaseModel):
    """Immutable published snapshot and provenance evidence.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_id: str
    version: int
    previous_version: int | None
    content_sha256: str
    snapshot: dict[str, Any]
    actor_id: str
    correlation_id: str
    acknowledgement: str | None
    published_at: datetime


class PublishSchemaDraftResponse(BaseModel):
    """Atomic publication result and advanced working draft.

    @skyhook-implements NFR-001
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    publication: SchemaPublicationResponse
    next_draft: SchemaDraftResponse


class _NoPublishedArtifacts:
    """Fail-safe catalog until the governed artifact context is integrated."""

    async def available_artifacts(
        self, tenant_id: UUID, draft: SchemaDraft
    ) -> Mapping[ArtifactKey, str]:
        return {}


class SchemaApiRuntime:
    """Long-lived schema adapters that create request-owned transactions.

    @skyhook-implements NFR-008
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    def __init__(self, settings: ApiSettings, *, engine: AsyncEngine | None = None) -> None:
        self.settings = settings
        self.engine = engine or create_schema_engine(settings.database, purpose="api-schemas")
        self.sessions: async_sessionmaker[AsyncSession] = create_schema_session_factory(self.engine)
        self.artifacts: SchemaArtifactCatalog = _NoPublishedArtifacts()

    async def close(self) -> None:
        """Dispose pooled database connections owned by the schema runtime."""
        await self.engine.dispose()

    def lifecycle(self, database_session: AsyncSession) -> ManageSchemaLifecycle:
        """Build the application service for one transaction."""
        return ManageSchemaLifecycle(
            PostgresSchemaRepository(database_session),
            self.artifacts,
        )


def _schema_id(value: str) -> SchemaId:
    try:
        return SchemaId(value)
    except ValueError as error:
        raise ApiError(400, "invalid_schema_id", "The schema identifier is invalid.") from error


def _content(value: SchemaDraftContentRequest) -> SchemaDraftContent:
    try:
        parsed = import_schema_draft_content(
            value.model_dump(by_alias=True), schema_id=SchemaId.new(), version=SchemaVersion(1)
        )
    except (TypeError, ValueError) as error:
        raise ApiError(
            400, "invalid_schema_definition", "The schema definition is invalid."
        ) from error
    return SchemaDraftContent(
        fields=parsed.fields,
        modules=parsed.modules,
        release_label=parsed.release_label,
        artifacts=parsed.artifacts,
    )


def _draft_response(stored: StoredSchemaDraft) -> SchemaDraftResponse:
    draft = stored.draft
    return SchemaDraftResponse(
        schema_id=draft.schema_id.value,
        version=draft.version.value,
        revision=stored.revision,
        content=export_schema_draft_content(draft),
        created_by=stored.created_by,
        updated_by=stored.updated_by,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


def _publication_response(stored: StoredSchemaPublication) -> SchemaPublicationResponse:
    publication = stored.publication
    provenance = publication.provenance
    return SchemaPublicationResponse(
        schema_id=publication.schema.schema_id.value,
        version=publication.schema.version.value,
        previous_version=(
            None if stored.previous_version is None else stored.previous_version.value
        ),
        content_sha256=publication.content_sha256,
        snapshot=json.loads(export_schema(publication.schema)),
        actor_id=provenance.actor_id,
        correlation_id=provenance.correlation_id,
        acknowledgement=provenance.acknowledgement,
        published_at=provenance.published_at,
    )


def _digest(operation: str, payload: BaseModel) -> str:
    canonical = json.dumps(
        {"operation": operation, "payload": payload.model_dump(mode="json", by_alias=True)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _event(runtime: SchemaApiRuntime, request: Request, event: str, **attributes: object) -> None:
    emit_security_event(
        event,
        service="api",
        environment=runtime.settings.environment,
        version=runtime.settings.version,
        correlation_id=request.state.correlation_id,
        attributes=attributes,
    )


async def _context(access_runtime: AccessApiRuntime, request: Request) -> SchemaCommandContext:
    token = session_token(request, access_runtime.settings.session)
    async with access_runtime.sessions.begin() as database_session:
        try:
            resolved = await ResolveTrustedContext(
                access_runtime.manage_sessions(database_session)
            ).resolve(
                token,
                correlation_id=request.state.correlation_id,
                now=datetime.now(UTC),
            )
        except AccessDeniedError as error:
            emit_security_event(
                "schema.context.denied",
                service="api",
                environment=access_runtime.settings.environment,
                version=access_runtime.settings.version,
                correlation_id=request.state.correlation_id,
                attributes={"outcome": "denied", "reason": error.reason.value},
            )
            if error.reason is AccessDenialReason.TENANT_CONTEXT_REQUIRED:
                mapped = ApiError(409, "tenant_context_required", "Select a tenant to continue.")
            elif error.reason is AccessDenialReason.SESSION_INACTIVE:
                mapped = ApiError(401, "session_invalid", "The session is invalid or expired.")
            else:
                mapped = ApiError(403, "access_denied", "The request is not authorized.")
            raise mapped from error
    trusted = resolved.context
    return SchemaCommandContext(
        tenant_id=UUID(trusted.tenant_id.value),
        actor_id=trusted.operator_id.value,
        capabilities=frozenset(item.value for item in trusted.capabilities),
        correlation_id=trusted.correlation_id,
    )


def _map_schema_error(error: Exception) -> ApiError:
    if isinstance(error, SchemaAuthorizationError):
        return ApiError(403, "access_denied", "The request is not authorized.")
    if isinstance(error, DraftNotFoundError):
        return ApiError(404, "schema_not_found", "The schema resource was not found.")
    if isinstance(error, DraftRevisionConflictError):
        return ApiError(409, "schema_revision_conflict", "The schema draft has changed.")
    if isinstance(error, PublicationAlreadyExistsError):
        return ApiError(409, "schema_version_conflict", "The schema version already exists.")
    if isinstance(error, IdempotencyKeyReuseError):
        return ApiError(
            409,
            "idempotency_key_reused",
            "The idempotency key was already used for different command content.",
        )
    if isinstance(error, ValueError):
        return ApiError(409, "schema_command_rejected", "The schema command was rejected.")
    raise error


def create_schema_router(runtime: SchemaApiRuntime, access_runtime: AccessApiRuntime) -> APIRouter:
    """Compose schema routes exclusively over schema application contracts.

    @skyhook-implements REQ-003
    @skyhook-implements REQ-012
    @skyhook-implements NFR-002
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """
    router = APIRouter(prefix="/api/v1/schemas", tags=["schemas"])

    async def mutate(
        operation: str,
        payload: BaseModel,
        request: Request,
        idempotency_key: str,
        execute: Any,
        response_status: int,
    ) -> JSONResponse:
        token = session_token(request, access_runtime.settings.session)
        require_csrf(request, token, request.headers.get(CSRF_HEADER_NAME))
        context = await _context(access_runtime, request)
        request_sha256 = _digest(operation, payload)
        try:
            async with runtime.sessions.begin() as database_session:
                receipts = PostgresSchemaCommandReceipts(database_session)
                replay = await receipts.claim(
                    context.tenant_id,
                    operation,
                    idempotency_key,
                    request_sha256,
                    actor_id=context.actor_id,
                    correlation_id=context.correlation_id,
                )
                if replay is not None:
                    _event(
                        runtime,
                        request,
                        "schema.command.replayed",
                        outcome="success",
                        operation=operation.partition(":")[0],
                        operator_id=context.actor_id,
                        tenant_id=str(context.tenant_id),
                    )
                    return JSONResponse(
                        status_code=replay.status_code, content=replay.response_body
                    )
                response_model = await execute(runtime.lifecycle(database_session), context)
                body = response_model.model_dump(mode="json", by_alias=True)
                await receipts.complete(
                    context.tenant_id,
                    operation,
                    idempotency_key,
                    SchemaCommandReceipt(response_status, body),
                )
        except Exception as error:
            _event(
                runtime,
                request,
                "schema.command.denied",
                outcome="denied",
                operation=operation.partition(":")[0],
                reason=type(error).__name__,
                operator_id=context.actor_id,
                tenant_id=str(context.tenant_id),
            )
            raise _map_schema_error(error) from error
        _event(
            runtime,
            request,
            f"schema.{operation.partition(':')[0]}.succeeded",
            outcome="success",
            operator_id=context.actor_id,
            tenant_id=str(context.tenant_id),
        )
        return JSONResponse(status_code=response_status, content=body)

    @router.post(
        "/drafts",
        operation_id="schemas_create_draft",
        response_model=SchemaDraftResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def create_draft(
        payload: CreateSchemaDraftRequest,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias=IDEMPOTENCY_HEADER_NAME, min_length=1, max_length=128)
        ],
    ) -> JSONResponse:
        async def execute(service: ManageSchemaLifecycle, context: SchemaCommandContext) -> Any:
            return _draft_response(await service.create_draft(context, _content(payload.content)))

        return await mutate("create_draft", payload, request, idempotency_key, execute, 201)

    @router.get(
        "/drafts",
        operation_id="schemas_list_drafts",
        response_model=SchemaDraftPageResponse,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def list_drafts(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        cursor: Annotated[str | None, Query()] = None,
    ) -> SchemaDraftPageResponse:
        context = await _context(access_runtime, request)
        try:
            cursor_id = None if cursor is None else _schema_id(cursor).value
            async with runtime.sessions.begin() as database_session:
                stored = await runtime.lifecycle(database_session).list_drafts(context)
        except Exception as error:
            raise _map_schema_error(error) from error
        candidates = [
            item for item in stored if cursor_id is None or item.draft.schema_id.value > cursor_id
        ]
        page = candidates[: limit + 1]
        has_next = len(page) > limit
        visible = page[:limit]
        return SchemaDraftPageResponse(
            items=tuple(_draft_response(item) for item in visible),
            next_cursor=(visible[-1].draft.schema_id.value if has_next else None),
        )

    @router.get(
        "/drafts/{schema_id}",
        operation_id="schemas_get_draft",
        response_model=SchemaDraftResponse,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def get_draft(schema_id: str, request: Request) -> SchemaDraftResponse:
        context = await _context(access_runtime, request)
        try:
            async with runtime.sessions.begin() as database_session:
                stored = await runtime.lifecycle(database_session).get_draft(
                    context, _schema_id(schema_id)
                )
        except Exception as error:
            raise _map_schema_error(error) from error
        if stored is None:
            raise ApiError(404, "schema_not_found", "The schema resource was not found.")
        return _draft_response(stored)

    @router.put(
        "/drafts/{schema_id}",
        operation_id="schemas_replace_draft",
        response_model=SchemaDraftResponse,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def replace_draft(
        schema_id: str,
        payload: ReplaceSchemaDraftRequest,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias=IDEMPOTENCY_HEADER_NAME, min_length=1, max_length=128)
        ],
    ) -> JSONResponse:
        identifier = _schema_id(schema_id)

        async def execute(service: ManageSchemaLifecycle, context: SchemaCommandContext) -> Any:
            stored = await service.replace_draft(
                context,
                identifier,
                expected_revision=payload.expected_revision,
                content=_content(payload.content),
            )
            return _draft_response(stored)

        operation = f"replace_draft:{identifier.value}"
        return await mutate(operation, payload, request, idempotency_key, execute, 200)

    @router.post(
        "/drafts/{schema_id}/publications",
        operation_id="schemas_publish_draft",
        response_model=PublishSchemaDraftResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def publish_draft(
        schema_id: str,
        payload: PublishSchemaDraftRequest,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias=IDEMPOTENCY_HEADER_NAME, min_length=1, max_length=128)
        ],
    ) -> JSONResponse:
        identifier = _schema_id(schema_id)

        async def execute(service: ManageSchemaLifecycle, context: SchemaCommandContext) -> Any:
            result = await service.publish_draft(
                context,
                identifier,
                expected_revision=payload.expected_revision,
                acknowledgement=payload.acknowledgement,
            )
            return PublishSchemaDraftResponse(
                publication=_publication_response(result.publication),
                next_draft=_draft_response(result.next_draft),
            )

        operation = f"publish_draft:{identifier.value}"
        return await mutate(operation, payload, request, idempotency_key, execute, 201)

    @router.get(
        "/{schema_id}/versions/{version}",
        operation_id="schemas_get_publication",
        response_model=SchemaPublicationResponse,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def get_publication(
        schema_id: str, version: int, request: Request
    ) -> SchemaPublicationResponse:
        context = await _context(access_runtime, request)
        try:
            requested_version = SchemaVersion(version)
            async with runtime.sessions.begin() as database_session:
                stored = await runtime.lifecycle(database_session).get_publication(
                    context, _schema_id(schema_id), requested_version
                )
        except Exception as error:
            raise _map_schema_error(error) from error
        if stored is None:
            raise ApiError(404, "schema_not_found", "The schema resource was not found.")
        return _publication_response(stored)

    return router
