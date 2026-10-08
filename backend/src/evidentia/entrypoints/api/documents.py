"""Versioned authenticated HTTP adapter for original-document custody.

@skyhook-implements REQ-001
@skyhook-implements REQ-012
@skyhook-implements REQ-015
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements CON-004
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Header, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict
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
from evidentia.modules.documents.application.ports import (
    CustodyAlreadyExistsError,
    CustodyPersistenceConflictError,
    StoredCustodyIntegrityError,
)
from evidentia.modules.documents.infrastructure.database import (
    create_document_engine,
    create_document_session_factory,
)
from evidentia.modules.documents.infrastructure.filesystem import LocalOriginalArtifactStore
from evidentia.modules.documents.infrastructure.transactional_repository import (
    TransactionalDocumentCustodyRepository,
)
from evidentia.modules.documents.public import (
    DOCUMENTS_READ,
    ArtifactPreservationError,
    DocumentAuthorizationError,
    DocumentCommandContext,
    DocumentCustody,
    DocumentId,
    IdempotencyConflictError,
    IdempotencyKey,
    MediaType,
    OriginalFilename,
    PreserveOriginalCommand,
    PreserveOriginalDocument,
    UploadInProgressError,
    UploadPolicy,
    UploadRejectedError,
)
from evidentia.runtime import emit_security_event

IDEMPOTENCY_HEADER_NAME = "Idempotency-Key"
_SESSION_SECURITY: dict[str, Any] = {"security": [{"sessionCookie": []}]}
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Invalid document request"},
    401: {"model": ErrorResponse, "description": "Authentication failed or expired"},
    403: {"model": ErrorResponse, "description": "Request is not authorized"},
    404: {"model": ErrorResponse, "description": "Document was not found"},
    409: {"model": ErrorResponse, "description": "Upload conflicts with current state"},
    413: {"model": ErrorResponse, "description": "Document exceeds the configured limit"},
    415: {"model": ErrorResponse, "description": "Document media type is unsupported"},
    503: {"model": ErrorResponse, "description": "Artifact storage is unavailable"},
}


class DocumentResponse(BaseModel):
    """Safe custody status without exposing a local filesystem path.

    @skyhook-implements REQ-001
    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    document_id: str
    status: str
    revision: int
    original_filename: str
    media_type: str
    byte_size: int
    content_sha256: str | None
    failure_code: str | None
    created_at: datetime
    updated_at: datetime


class DocumentApiRuntime:
    """Long-lived database and local-artifact adapters for document requests.

    @skyhook-implements NFR-004
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    def __init__(
        self,
        settings: ApiSettings,
        *,
        engine: AsyncEngine | None = None,
        artifact_root: Path | None = None,
    ) -> None:
        self.settings = settings
        self.engine = engine or create_document_engine(settings.database, purpose="api-documents")
        self.sessions: async_sessionmaker[AsyncSession] = create_document_session_factory(
            self.engine
        )
        self.artifacts = LocalOriginalArtifactStore(artifact_root or settings.storage.root)
        self.policy = UploadPolicy(maximum_bytes=settings.storage.maximum_upload_bytes)

    async def close(self) -> None:
        """Dispose pooled database connections owned by this runtime."""
        await self.engine.dispose()


def _response(custody: DocumentCustody) -> DocumentResponse:
    artifact = custody.artifact
    return DocumentResponse(
        document_id=custody.document_id.value,
        status=custody.status.value,
        revision=custody.revision,
        original_filename=custody.source.filename.value,
        media_type=custody.source.media_type.value,
        byte_size=custody.source.byte_size,
        content_sha256=None if artifact is None else artifact.digest.value,
        failure_code=None if custody.failure_code is None else custody.failure_code.value,
        created_at=custody.created_at,
        updated_at=custody.updated_at,
    )


async def _context(access_runtime: AccessApiRuntime, request: Request) -> DocumentCommandContext:
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
            if error.reason is AccessDenialReason.TENANT_CONTEXT_REQUIRED:
                mapped = ApiError(409, "tenant_context_required", "Select a tenant to continue.")
            elif error.reason is AccessDenialReason.SESSION_INACTIVE:
                mapped = ApiError(401, "session_invalid", "The session is invalid or expired.")
            else:
                mapped = ApiError(403, "access_denied", "The request is not authorized.")
            raise mapped from error
    trusted = resolved.context
    return DocumentCommandContext(
        tenant_id=UUID(trusted.tenant_id.value),
        actor_id=trusted.operator_id.value,
        capabilities=frozenset(item.value for item in trusted.capabilities),
        correlation_id=trusted.correlation_id,
    )


async def _read_limited(upload: UploadFile, maximum_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(1024 * 1024):
        size += len(chunk)
        if size > maximum_bytes:
            raise ApiError(
                413,
                "document_too_large",
                f"The document exceeds the configured {maximum_bytes}-byte upload limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _map_error(error: Exception) -> ApiError:
    if isinstance(error, DocumentAuthorizationError):
        return ApiError(403, "access_denied", "The request is not authorized.")
    if isinstance(error, IdempotencyConflictError):
        return ApiError(409, "idempotency_key_reused", "The retry key belongs to other content.")
    if isinstance(error, (UploadInProgressError, CustodyAlreadyExistsError)):
        return ApiError(409, "upload_in_progress", "A matching upload is already in progress.")
    if isinstance(error, CustodyPersistenceConflictError):
        return ApiError(409, "document_revision_conflict", "Document custody has changed.")
    if isinstance(error, ArtifactPreservationError):
        return ApiError(503, "artifact_storage_unavailable", "The original could not be stored.")
    if isinstance(error, StoredCustodyIntegrityError):
        return ApiError(500, "stored_document_invalid", "Stored document custody is invalid.")
    if isinstance(error, UploadRejectedError):
        if "media type" in str(error):
            return ApiError(415, "unsupported_document_type", "The document type is unsupported.")
        return ApiError(413, "document_too_large", "The document exceeds the upload limit.")
    if isinstance(error, ValueError):
        return ApiError(400, "invalid_document", "The document request is invalid.")
    raise error


def _event(runtime: DocumentApiRuntime, request: Request, event: str, **attributes: object) -> None:
    emit_security_event(
        event,
        service="api",
        environment=runtime.settings.environment,
        version=runtime.settings.version,
        correlation_id=request.state.correlation_id,
        attributes=attributes,
    )


def create_document_router(
    runtime: DocumentApiRuntime, access_runtime: AccessApiRuntime
) -> APIRouter:
    """Compose upload and status routes over document-owned application ports.

    @skyhook-implements REQ-001
    @skyhook-implements REQ-012
    @skyhook-implements NFR-002
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """
    router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

    @router.post(
        "",
        operation_id="documents_upload_original",
        response_model=DocumentResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def upload_original(
        request: Request,
        document: Annotated[UploadFile, File(description="Original document bytes")],
        idempotency_key: Annotated[
            str, Header(alias=IDEMPOTENCY_HEADER_NAME, min_length=1, max_length=128)
        ],
    ) -> DocumentResponse:
        token = session_token(request, access_runtime.settings.session)
        require_csrf(request, token, request.headers.get(CSRF_HEADER_NAME))
        context = await _context(access_runtime, request)
        try:
            content = await _read_limited(document, runtime.policy.maximum_bytes)
            command = PreserveOriginalCommand(
                OriginalFilename(document.filename or "document"),
                MediaType(document.content_type or "application/octet-stream"),
                content,
                IdempotencyKey(idempotency_key),
            )
            custody = await PreserveOriginalDocument(
                TransactionalDocumentCustodyRepository(runtime.sessions),
                runtime.artifacts,
                policy=runtime.policy,
            ).execute(context, command, now=datetime.now(UTC))
        except Exception as error:
            _event(
                runtime,
                request,
                "document.upload.failed",
                outcome="failed",
                reason=type(error).__name__,
            )
            raise _map_error(error) from error
        _event(
            runtime,
            request,
            "document.upload.preserved",
            outcome="success",
            document_id=custody.document_id.value,
            operator_id=context.actor_id,
            tenant_id=str(context.tenant_id),
        )
        return _response(custody)

    @router.get(
        "/{document_id}",
        operation_id="documents_get_custody",
        response_model=DocumentResponse,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def get_custody(document_id: str, request: Request) -> DocumentResponse:
        context = await _context(access_runtime, request)
        if DOCUMENTS_READ not in context.capabilities:
            raise ApiError(403, "access_denied", "The request is not authorized.")
        try:
            identity = DocumentId(document_id)
            custody = await TransactionalDocumentCustodyRepository(runtime.sessions).get(
                context.tenant_id, identity
            )
        except Exception as error:
            raise _map_error(error) from error
        if custody is None:
            raise ApiError(404, "document_not_found", "The document was not found.")
        return _response(custody)

    return router
