"""Versioned HTTP adapter for local authentication and trusted access context.

@skyhook-implements REQ-012
@skyhook-implements NFR-006
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from evidentia.config.settings import ApiSettings
from evidentia.entrypoints.api.errors import ApiError, ErrorResponse
from evidentia.entrypoints.api.security import (
    CSRF_HEADER_NAME,
    clear_session_cookies,
    require_csrf,
    session_token,
    set_session_cookies,
)
from evidentia.modules.access.infrastructure.database import (
    create_access_engine,
    create_access_session_factory,
)
from evidentia.modules.access.infrastructure.passwords import Argon2idPasswordHasher
from evidentia.modules.access.infrastructure.repository import (
    PostgresCredentialRepository,
    PostgresMembershipRepository,
    PostgresOperatorRepository,
    PostgresSessionRepository,
    PostgresTenantRepository,
)
from evidentia.modules.access.infrastructure.throttle import InMemoryAuthenticationThrottle
from evidentia.modules.access.infrastructure.tokens import SecureSessionTokenProvider
from evidentia.modules.access.public import (
    AccessDenialReason,
    AccessDeniedError,
    AuthenticateLocalOperator,
    AuthenticationDeniedError,
    AuthenticationSecret,
    LocalAuthenticationRequest,
    LoginIdentifier,
    ManageSessions,
    MembershipStatus,
    OperatorId,
    ResolveTrustedContext,
    SessionDenialReason,
    SessionDeniedError,
    TenantId,
    TenantStatus,
)
from evidentia.runtime import emit_security_event

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Invalid request"},
    401: {"model": ErrorResponse, "description": "Authentication failed or expired"},
    403: {"model": ErrorResponse, "description": "Request is not authorized"},
    409: {"model": ErrorResponse, "description": "Tenant context is required"},
    429: {"model": ErrorResponse, "description": "Authentication is temporarily throttled"},
}
_SESSION_SECURITY: dict[str, Any] = {"security": [{"sessionCookie": []}]}


class LoginRequest(BaseModel):
    """Validated local login material and optional initial tenant selection.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    model_config = ConfigDict(extra="forbid")

    login_identifier: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)
    tenant_id: str | None = None


class TenantSelectionRequest(BaseModel):
    """Validated request to rotate a session into another tenant.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str


class TenantSummary(BaseModel):
    """Display-safe tenant option available to the authenticated operator.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str
    slug: str
    display_name: str


class SessionResponse(BaseModel):
    """Browser session result without raw token or secret material.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    operator_id: str
    active_tenant_id: str | None
    tenant_selection_required: bool
    available_tenants: tuple[TenantSummary, ...]


class CurrentContextResponse(BaseModel):
    """Current database-backed operator and tenant context.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    operator_id: str
    login_identifier: str
    display_name: str
    tenant_id: str
    tenant_slug: str
    tenant_name: str
    membership_id: str
    capabilities: tuple[str, ...]
    session_id: str
    correlation_id: str
    authenticated_at: datetime


class AccessApiRuntime:
    """Long-lived adapters used to create request-owned access transactions.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(
        self,
        settings: ApiSettings,
        *,
        engine: AsyncEngine | None = None,
    ) -> None:
        self.settings = settings
        self.engine = engine or create_access_engine(settings.database, purpose="api-access")
        self.sessions: async_sessionmaker[AsyncSession] = create_access_session_factory(self.engine)
        self.tokens = SecureSessionTokenProvider()
        self.passwords = Argon2idPasswordHasher()
        self.throttle = InMemoryAuthenticationThrottle()

    async def close(self) -> None:
        """Dispose pooled database connections owned by the API runtime."""
        await self.engine.dispose()

    def manage_sessions(self, database_session: AsyncSession) -> ManageSessions:
        """Create the application service over one caller-owned transaction."""
        return ManageSessions(
            PostgresSessionRepository(database_session),
            PostgresOperatorRepository(database_session),
            PostgresTenantRepository(database_session),
            PostgresMembershipRepository(database_session),
            self.tokens,
            idle_timeout_seconds=self.settings.session.idle_timeout_seconds,
            absolute_timeout_seconds=self.settings.session.absolute_timeout_seconds,
        )


def _tenant_id(value: str) -> TenantId:
    try:
        return TenantId(value)
    except ValueError as error:
        raise ApiError(400, "invalid_tenant", "The tenant identifier is invalid.") from error


def _map_session_denial(error: SessionDeniedError) -> ApiError:
    if error.reason in {
        SessionDenialReason.TENANT_INACTIVE,
        SessionDenialReason.MEMBERSHIP_INACTIVE,
    }:
        return ApiError(403, "tenant_not_available", "The tenant is not available.")
    return ApiError(401, "session_invalid", "The session is invalid or expired.")


def _map_access_denial(error: AccessDeniedError) -> ApiError:
    if error.reason is AccessDenialReason.TENANT_CONTEXT_REQUIRED:
        return ApiError(409, "tenant_context_required", "Select a tenant to continue.")
    if error.reason is AccessDenialReason.SESSION_INACTIVE:
        return ApiError(401, "session_invalid", "The session is invalid or expired.")
    return ApiError(403, "access_denied", "The request is not authorized.")


def _login_fingerprint(value: str) -> str:
    return hashlib.sha256(value.strip().casefold().encode()).hexdigest()


def _event(
    runtime: AccessApiRuntime,
    request: Request,
    event: str,
    **attributes: object,
) -> None:
    emit_security_event(
        event,
        service="api",
        environment=runtime.settings.environment,
        version=runtime.settings.version,
        correlation_id=request.state.correlation_id,
        attributes=attributes,
    )


async def _available_tenants(
    database_session: AsyncSession,
    operator_id: OperatorId,
) -> tuple[TenantSummary, ...]:
    memberships = PostgresMembershipRepository(database_session)
    tenants = PostgresTenantRepository(database_session)
    results: list[TenantSummary] = []
    for membership in await memberships.list_for_operator(operator_id):
        if membership.status is not MembershipStatus.ACTIVE:
            continue
        tenant = await tenants.get(membership.tenant_id)
        if tenant is not None and tenant.status is TenantStatus.ACTIVE:
            results.append(
                TenantSummary(
                    tenant_id=tenant.tenant_id.value,
                    slug=tenant.slug.value,
                    display_name=tenant.display_name,
                )
            )
    return tuple(sorted(results, key=lambda item: item.slug))


def create_access_router(runtime: AccessApiRuntime) -> APIRouter:
    """Compose the versioned access router over application-layer services.

    @skyhook-implements REQ-012
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    router = APIRouter(prefix="/api/v1/access", tags=["access"])

    @router.post(
        "/sessions",
        operation_id="access_login_local",
        summary="Create a local browser session",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_ERROR_RESPONSES,
    )
    async def login(payload: LoginRequest, request: Request, response: Response) -> SessionResponse:
        now = datetime.now(UTC)
        try:
            identifier = LoginIdentifier(payload.login_identifier)
        except ValueError as error:
            _event(
                runtime,
                request,
                "access.login.denied",
                outcome="denied",
                reason="invalid_credentials",
                login_identifier_sha256=_login_fingerprint(payload.login_identifier),
            )
            raise ApiError(401, "authentication_failed", "The credentials are invalid.") from error
        async with runtime.sessions.begin() as database_session:
            try:
                identity = await AuthenticateLocalOperator(
                    PostgresOperatorRepository(database_session),
                    PostgresCredentialRepository(database_session),
                    runtime.passwords,
                    runtime.throttle,
                ).execute(
                    LocalAuthenticationRequest(
                        identifier,
                        AuthenticationSecret(payload.password.get_secret_value()),
                    ),
                    now=now,
                )
            except AuthenticationDeniedError as error:
                _event(
                    runtime,
                    request,
                    "access.login.denied",
                    outcome="denied",
                    reason="invalid_credentials",
                    login_identifier_sha256=_login_fingerprint(identifier.value),
                    retry_after_seconds=error.retry_after_seconds,
                )
                status_code = 429 if error.retry_after_seconds else 401
                headers = (
                    {"Retry-After": str(error.retry_after_seconds)}
                    if error.retry_after_seconds
                    else None
                )
                raise ApiError(
                    status_code,
                    "authentication_failed",
                    "The credentials are invalid or authentication is temporarily unavailable.",
                    headers=headers,
                ) from error

            available = await _available_tenants(database_session, identity.operator_id)
            selected = _tenant_id(payload.tenant_id) if payload.tenant_id else None
            if selected is None and len(available) == 1:
                selected = TenantId(available[0].tenant_id)
            try:
                issued = await runtime.manage_sessions(database_session).issue(
                    identity.operator_id,
                    now=now,
                    active_tenant_id=selected,
                )
            except SessionDeniedError as error:
                raise ApiError(
                    403, "tenant_not_available", "The tenant is not available."
                ) from error

        set_session_cookies(response, issued.token, runtime.settings.session)
        _event(
            runtime,
            request,
            "access.login.succeeded",
            outcome="success",
            operator_id=identity.operator_id.value,
            tenant_id=(
                None
                if issued.session.active_tenant_id is None
                else issued.session.active_tenant_id.value
            ),
            session_id=issued.session.session_id.value,
        )
        return SessionResponse(
            operator_id=identity.operator_id.value,
            active_tenant_id=(
                None
                if issued.session.active_tenant_id is None
                else issued.session.active_tenant_id.value
            ),
            tenant_selection_required=issued.session.active_tenant_id is None,
            available_tenants=available,
        )

    @router.get(
        "/session",
        operation_id="access_get_session",
        summary="Inspect the current browser session",
        response_model=SessionResponse,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def current_session(request: Request) -> SessionResponse:
        """Restore non-secret session and tenant-selection state for the browser.

        @skyhook-implements REQ-012
        @skyhook-implements NFR-002
        @skyhook-story STORY-017
        """
        token = session_token(request, runtime.settings.session)
        async with runtime.sessions.begin() as database_session:
            manager = runtime.manage_sessions(database_session)
            try:
                validated = await manager.validate(token, now=datetime.now(UTC))
            except SessionDeniedError as error:
                _event(
                    runtime,
                    request,
                    "access.session_restore.denied",
                    outcome="denied",
                    reason=error.reason.value,
                )
                raise _map_session_denial(error) from error
            available = await _available_tenants(
                database_session,
                validated.session.operator_id,
            )
        active_tenant_id = validated.session.active_tenant_id
        return SessionResponse(
            operator_id=validated.session.operator_id.value,
            active_tenant_id=(None if active_tenant_id is None else active_tenant_id.value),
            tenant_selection_required=active_tenant_id is None,
            available_tenants=available,
        )

    @router.delete(
        "/session",
        operation_id="access_logout",
        summary="Revoke the current browser session",
        status_code=status.HTTP_204_NO_CONTENT,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def logout(
        request: Request,
        response: Response,
        csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
    ) -> None:
        token = session_token(request, runtime.settings.session)
        try:
            require_csrf(request, token, csrf_header)
        except ApiError:
            _event(
                runtime,
                request,
                "access.logout.denied",
                outcome="denied",
                reason="csrf_rejected",
            )
            raise
        async with runtime.sessions.begin() as database_session:
            revoked = await runtime.manage_sessions(database_session).logout(
                token, now=datetime.now(UTC)
            )
        clear_session_cookies(response, runtime.settings.session)
        _event(
            runtime,
            request,
            "access.logout.succeeded",
            outcome="success",
            operator_id=None if revoked is None else revoked.operator_id.value,
            tenant_id=(
                None
                if revoked is None or revoked.active_tenant_id is None
                else revoked.active_tenant_id.value
            ),
            session_id=None if revoked is None else revoked.session_id.value,
        )

    @router.get(
        "/context",
        operation_id="access_get_current_context",
        summary="Get the current trusted operator and tenant context",
        response_model=CurrentContextResponse,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def current_context(request: Request) -> CurrentContextResponse:
        token = session_token(request, runtime.settings.session)
        async with runtime.sessions.begin() as database_session:
            try:
                resolved = await ResolveTrustedContext(
                    runtime.manage_sessions(database_session)
                ).resolve(
                    token,
                    correlation_id=request.state.correlation_id,
                    now=datetime.now(UTC),
                )
            except AccessDeniedError as error:
                _event(
                    runtime,
                    request,
                    "access.context.denied",
                    outcome="denied",
                    reason=error.reason.value,
                )
                raise _map_access_denial(error) from error
        context = resolved.context
        return CurrentContextResponse(
            operator_id=context.operator_id.value,
            login_identifier=resolved.operator.login_identifier.value,
            display_name=resolved.operator.display_name,
            tenant_id=context.tenant_id.value,
            tenant_slug=resolved.tenant.slug.value,
            tenant_name=resolved.tenant.display_name,
            membership_id=context.membership_id.value,
            capabilities=tuple(item.value for item in sorted(context.capabilities)),
            session_id=context.session_id.value,
            correlation_id=context.correlation_id,
            authenticated_at=context.authenticated_at,
        )

    @router.put(
        "/session/tenant",
        operation_id="access_select_tenant",
        summary="Rotate the current session into an authorized tenant",
        response_model=SessionResponse,
        responses=_ERROR_RESPONSES,
        openapi_extra=_SESSION_SECURITY,
    )
    async def select_tenant(
        payload: TenantSelectionRequest,
        request: Request,
        response: Response,
        csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
    ) -> SessionResponse:
        token = session_token(request, runtime.settings.session)
        try:
            require_csrf(request, token, csrf_header)
        except ApiError:
            _event(
                runtime,
                request,
                "access.tenant_selection.denied",
                outcome="denied",
                reason="csrf_rejected",
            )
            raise
        tenant_id = _tenant_id(payload.tenant_id)
        async with runtime.sessions.begin() as database_session:
            manager = runtime.manage_sessions(database_session)
            try:
                issued = await manager.select_tenant(
                    token,
                    tenant_id,
                    now=datetime.now(UTC),
                )
                available = await _available_tenants(
                    database_session,
                    issued.session.operator_id,
                )
            except SessionDeniedError as error:
                _event(
                    runtime,
                    request,
                    "access.tenant_selection.denied",
                    outcome="denied",
                    reason=error.reason.value,
                    requested_tenant_id=tenant_id.value,
                )
                raise _map_session_denial(error) from error
        set_session_cookies(response, issued.token, runtime.settings.session)
        _event(
            runtime,
            request,
            "access.tenant_selection.succeeded",
            outcome="success",
            rotated=True,
            operator_id=issued.session.operator_id.value,
            tenant_id=tenant_id.value,
            session_id=issued.session.session_id.value,
        )
        return SessionResponse(
            operator_id=issued.session.operator_id.value,
            active_tenant_id=tenant_id.value,
            tenant_selection_required=False,
            available_tenants=available,
        )

    return router
