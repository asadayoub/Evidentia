"""Unit tests for browser credential security attributes."""

from fastapi import Response

from evidentia.config.settings import SessionSettings
from evidentia.entrypoints.api.security import set_session_cookies
from evidentia.modules.access.public import OpaqueSessionToken


def test_secure_environment_sets_secure_session_and_csrf_cookies() -> None:
    """Keep both cookies secure while exposing only the CSRF proof to scripts.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    response = Response()
    settings = SessionSettings(
        secret="0123456789abcdef0123456789abcdef",
        cookie_secure=True,
        cookie_samesite="strict",
    )

    set_session_cookies(response, OpaqueSessionToken("x" * 48), settings)

    headers = response.headers.getlist("set-cookie")
    assert len(headers) == 2
    assert all("Secure" in header and "SameSite=strict" in header for header in headers)
    assert "HttpOnly" in headers[0] and "Path=/api/v1" in headers[0]
    assert "HttpOnly" not in headers[1] and "Path=/" in headers[1]
