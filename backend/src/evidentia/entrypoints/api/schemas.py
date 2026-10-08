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
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
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
    InspectedSchemaPackage,
    ManageSchemaLifecycle,
    SchemaArtifactCatalog,
    SchemaAuthorizationError,
    SchemaCommandContext,
    SchemaDraft,
    SchemaDraftContent,
    SchemaId,
    SchemaImportPreview,
    SchemaVersion,
    export_schema,
    export_schema_draft,
    export_schema_draft_content,
    import_schema_draft_content,
    inspect_schema_package,
    preview_schema_import,
)
from evidentia.runtime import emit_security_event

IDEMPOTENCY_HEADER_NAME = "Idempotency-Key"
MAX_SCHEMA_PACKAGE_BYTES = 1_048_576
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


class SchemaPackageRequest(BaseModel):
    """Untrusted portable package accepted only after domain validation.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story STORY-018
    """

    model_config = ConfigDict(extra="forbid")
    package: dict[str, Any]


class PreviewSchemaImportRequest(SchemaPackageRequest):
    """Mutation-free package preview against a new or existing draft.

    @skyhook-implements REQ-003
    @skyhook-story STORY-018
    """

    target_schema_id: str | None = None


class ApplySchemaImportRequest(SchemaPackageRequest):
    """Create or revision-guardedly replace a draft from validated content.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-story STORY-018
    """

    target_schema_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_target(self) -> ApplySchemaImportRequest:
        """Require revision and target identity together."""
        if (self.target_schema_id is None) != (self.expected_revision is None):
            raise ValueError("target_schema_id and expected_revision must be supplied together")
        return self


class SchemaCompatibilityChangeResponse(BaseModel):
    """One stable path-addressed package difference.

    @skyhook-implements REQ-003
    @skyhook-story STORY-018
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    level: str
    path: str | None
    message: str


class SchemaCompatibilityResponse(BaseModel):
    """Deterministic compatibility classification for an existing target.

    @skyhook-implements REQ-003
    @skyhook-story STORY-018
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    level: str
    requires_acknowledgement: bool
    changes: tuple[SchemaCompatibilityChangeResponse, ...]


class SchemaImportPreviewResponse(BaseModel):
    """Validated package provenance, editable content, target, and impact.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story STORY-018
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: str
    format: str
    envelope_version: int
    source_schema_id: str
    source_schema_version: int
    canonical_sha256: str
    creates_new_draft: bool
    target_schema_id: str | None
    target_revision: int | None
    content: dict[str, Any]
    compatibility: SchemaCompatibilityResponse | None


class ApplySchemaImportResponse(BaseModel):
    """Applied draft and package evidence returned by an idempotent command.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-story STORY-018
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    draft: SchemaDraftResponse
    package_sha256: str
    created: bool


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


def _package(value: Mapping[str, Any]) -> InspectedSchemaPackage:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode()) > MAX_SCHEMA_PACKAGE_BYTES:
        raise ApiError(400, "schema_package_too_large", "The schema package is too large.")
    try:
        return inspect_schema_package(encoded)
    except (TypeError, ValueError) as error:
        raise ApiError(400, "invalid_schema_package", "The schema package is invalid.") from error


def _preview_response(preview: SchemaImportPreview) -> SchemaImportPreviewResponse:
    report = preview.compatibility
    compatibility = (
        None
        if report is None
        else SchemaCompatibilityResponse(
            level=report.level.value,
            requires_acknowledgement=report.requires_acknowledgement,
            changes=tuple(
                SchemaCompatibilityChangeResponse(
                    code=change.code.value,
                    level=change.level.value,
                    path=None if change.path is None else str(change.path),
                    message=change.message,
                )
                for change in report.changes
            ),
        )
    )
    package = preview.package
    synthetic = SchemaDraft(
        schema_id=SchemaId(package.source_schema_id),
        version=SchemaVersion(package.source_schema_version),
        fields=package.content.fields,
        modules=package.content.modules,
        release_label=package.content.release_label,
        artifacts=package.content.artifacts,
    )
    return SchemaImportPreviewResponse(
        kind=package.kind.value,
        format=package.format,
        envelope_version=package.envelope_version,
        source_schema_id=package.source_schema_id,
        source_schema_version=package.source_schema_version,
        canonical_sha256=package.canonical_sha256,
        creates_new_draft=preview.creates_new_draft,
        target_schema_id=preview.target_schema_id,
        target_revision=preview.target_revision,
        content=export_schema_draft_content(synthetic),
        compatibility=compatibility,
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


def _json_object(payload: bytes) -> dict[str, Any]:
    parsed: object = json.loads(payload)
    if not isinstance(parsed, dict):
        raise RuntimeError("canonical schema export must be a JSON object")
    return cast(dict[str, Any], parsed)


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
    @skyhook-story 265YM4FNANJAH2J338BKAWFXDM
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

    @router.get(
        "/drafts/{schema_id}/package",
        operation_id="schemas_export_draft_package",
        response_model=dict[str, Any],
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def export_draft_package(schema_id: str, request: Request) -> dict[str, Any]:
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
        _event(
            runtime,
            request,
            "schema.package.exported",
            outcome="success",
            package_kind="draft",
            schema_id=stored.draft.schema_id.value,
            operator_id=context.actor_id,
            tenant_id=str(context.tenant_id),
        )
        return _json_object(export_schema_draft(stored.draft))

    @router.post(
        "/imports/preview",
        operation_id="schemas_preview_import",
        response_model=SchemaImportPreviewResponse,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def preview_import(
        payload: PreviewSchemaImportRequest, request: Request
    ) -> SchemaImportPreviewResponse:
        token = session_token(request, access_runtime.settings.session)
        require_csrf(request, token, request.headers.get(CSRF_HEADER_NAME))
        context = await _context(access_runtime, request)
        package = _package(payload.package)
        try:
            async with runtime.sessions.begin() as database_session:
                service = runtime.lifecycle(database_session)
                service.authorize_read(context)
                stored = (
                    None
                    if payload.target_schema_id is None
                    else await service.get_draft(context, _schema_id(payload.target_schema_id))
                )
        except Exception as error:
            raise _map_schema_error(error) from error
        if payload.target_schema_id is not None and stored is None:
            raise ApiError(404, "schema_not_found", "The schema resource was not found.")
        preview = preview_schema_import(
            package,
            target=None if stored is None else stored.draft,
            target_revision=None if stored is None else stored.revision,
        )
        _event(
            runtime,
            request,
            "schema.import.previewed",
            outcome="success",
            package_sha256=package.canonical_sha256,
            target="new" if stored is None else stored.draft.schema_id.value,
            operator_id=context.actor_id,
            tenant_id=str(context.tenant_id),
        )
        return _preview_response(preview)

    @router.post(
        "/imports",
        operation_id="schemas_apply_import",
        response_model=ApplySchemaImportResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def apply_import(
        payload: ApplySchemaImportRequest,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias=IDEMPOTENCY_HEADER_NAME, min_length=1, max_length=128)
        ],
    ) -> JSONResponse:
        package = _package(payload.package)
        target = None if payload.target_schema_id is None else _schema_id(payload.target_schema_id)

        async def execute(service: ManageSchemaLifecycle, context: SchemaCommandContext) -> Any:
            if target is None:
                stored = await service.create_draft(context, package.content)
                created = True
            else:
                assert payload.expected_revision is not None
                stored = await service.replace_draft(
                    context,
                    target,
                    expected_revision=payload.expected_revision,
                    content=package.content,
                )
                created = False
            return ApplySchemaImportResponse(
                draft=_draft_response(stored),
                package_sha256=package.canonical_sha256,
                created=created,
            )

        operation_target = "new" if target is None else target.value
        return await mutate(
            f"apply_import:{operation_target}",
            payload,
            request,
            idempotency_key,
            execute,
            201,
        )

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

    @router.get(
        "/{schema_id}/versions/{version}/package",
        operation_id="schemas_export_publication_package",
        response_model=dict[str, Any],
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def export_publication_package(
        schema_id: str, version: int, request: Request
    ) -> dict[str, Any]:
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
        publication = stored.publication
        _event(
            runtime,
            request,
            "schema.package.exported",
            outcome="success",
            package_kind="publication",
            schema_id=publication.schema.schema_id.value,
            schema_version=publication.schema.version.value,
            operator_id=context.actor_id,
            tenant_id=str(context.tenant_id),
        )
        return _json_object(export_schema(publication.schema))

    return router
