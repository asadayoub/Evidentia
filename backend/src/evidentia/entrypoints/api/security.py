"""Browser-facing cookie, CSRF, origin, correlation, and header policy.

@skyhook-implements REQ-012
@skyhook-implements NFR-006
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Final
from uuid import uuid4

from fastapi import Request, Response

from evidentia.config.settings import SessionSettings
from evidentia.entrypoints.api.errors import ApiError
from evidentia.modules.access.public import OpaqueSessionToken

CSRF_COOKIE_NAME: Final = "evidentia_csrf"
CSRF_HEADER_NAME: Final = "x-csrf-token"
CORRELATION_HEADER_NAME: Final = "x-correlation-id"
COOKIE_PATH: Final = "/api/v1"
CSRF_COOKIE_PATH: Final = "/"
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def correlation_id(request: Request) -> str:
    """Use a valid caller correlation ID or create an opaque server value.

    @skyhook-implements NFR-006
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    supplied = request.headers.get(CORRELATION_HEADER_NAME)
    if supplied is not None and _CORRELATION_ID.fullmatch(supplied):
        return supplied
    return str(uuid4())


def session_token(request: Request, settings: SessionSettings) -> OpaqueSessionToken:
    """Read the opaque bearer only from the configured HttpOnly cookie.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    raw = request.cookies.get(settings.cookie_name)
    if raw is None:
        raise ApiError(401, "session_required", "Authentication is required.")
    try:
        return OpaqueSessionToken(raw)
    except ValueError as error:
        raise ApiError(401, "session_invalid", "The session is invalid or expired.") from error


def csrf_token(token: OpaqueSessionToken) -> str:
    """Derive a session-bound CSRF proof without exposing the bearer token.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    return hmac.new(
        token.reveal().encode(),
        b"evidentia-browser-csrf-v1",
        hashlib.sha256,
    ).hexdigest()


def require_csrf(
    request: Request,
    token: OpaqueSessionToken,
    submitted_header: str | None = None,
) -> None:
    """Require matching cookie/header proof bound to the current session.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    cookie = request.cookies.get(CSRF_COOKIE_NAME)
    header = submitted_header or request.headers.get(CSRF_HEADER_NAME)
    expected = csrf_token(token)
    if (
        cookie is None
        or header is None
        or not hmac.compare_digest(cookie, header)
        or not hmac.compare_digest(header, expected)
    ):
        raise ApiError(403, "csrf_rejected", "The request could not be verified.")


def set_session_cookies(
    response: Response,
    token: OpaqueSessionToken,
    settings: SessionSettings,
) -> None:
    """Write the bearer and its readable session-bound CSRF proof.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    response.set_cookie(
        settings.cookie_name,
        token.reveal(),
        max_age=settings.absolute_timeout_seconds,
        path=COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token(token),
        max_age=settings.absolute_timeout_seconds,
        path=CSRF_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=False,
        samesite=settings.cookie_samesite,
    )


def clear_session_cookies(response: Response, settings: SessionSettings) -> None:
    """Expire browser credentials using the same scope and security attributes.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    response.delete_cookie(
        settings.cookie_name,
        path=COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path=CSRF_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=False,
        samesite=settings.cookie_samesite,
    )
