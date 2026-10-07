"""Browser-level access API proof against disposable native PostgreSQL.

@skyhook-implements REQ-012
@skyhook-implements NFR-006
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any

import pytest
from backend.tests.integration.support import DisposablePostgresDatabase
from fastapi import FastAPI

from evidentia.config.settings import ApiSettings, IdentitySettings, SessionSettings
from evidentia.entrypoints.api import create_app
from evidentia.entrypoints.cli.identity import bootstrap_configured_identity

pytestmark = pytest.mark.postgres

_PASSWORD = "a-unique-api-password"
_ORIGIN = "http://localhost:3000"


@dataclass(frozen=True, slots=True)
class _HttpResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        return next((value for key, value in self.headers if key == lowered), None)

    def headers_for(self, name: str) -> tuple[str, ...]:
        lowered = name.lower()
        return tuple(value for key, value in self.headers if key == lowered)

    def json(self) -> dict[str, Any]:
        return json.loads(self.body)


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> _HttpResponse:
    payload = b"" if body is None else json.dumps(body).encode()
    request_headers = {"host": "testserver", **(headers or {})}
    if body is not None:
        request_headers["content-type"] = "application/json"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (key.lower().encode(), value.encode()) for key, value in request_headers.items()
        ],
        "client": ("127.0.0.1", 43210),
        "server": ("testserver", 80),
    }
    request_sent = False
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )
    return _HttpResponse(
        start["status"],
        tuple((key.decode(), value.decode()) for key, value in start["headers"]),
        response_body,
    )


def _cookies(response: _HttpResponse) -> dict[str, str]:
    values: dict[str, str] = {}
    for header in response.headers_for("set-cookie"):
        parsed = SimpleCookie()
        parsed.load(header)
        values.update({key: morsel.value for key, morsel in parsed.items()})
    return values


def _cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookies.items())


async def _exercise_access_api(database: DisposablePostgresDatabase) -> None:
    settings = ApiSettings(
        database=database.settings,
        identity=IdentitySettings(
            bootstrap_login_identifier="owner@example.com",
            bootstrap_display_name="Initial Owner",
            bootstrap_tenant_slug="review-team",
            bootstrap_tenant_name="Review Team",
            bootstrap_password=_PASSWORD,
        ),
        session=SessionSettings(
            secret="0123456789abcdef0123456789abcdef",
            idle_timeout_seconds=900,
            absolute_timeout_seconds=7_200,
            cookie_name="evidentia_auth",
        ),
    )
    bootstrap = await bootstrap_configured_identity(settings)
    app = create_app(settings)
    try:
        rejected_origin = await _request(
            app,
            "POST",
            "/api/v1/access/sessions",
            body={"login_identifier": "owner@example.com", "password": _PASSWORD},
            headers={"origin": "https://attacker.example"},
        )
        assert rejected_origin.status == 403
        assert rejected_origin.json()["code"] == "origin_rejected"

        login = await _request(
            app,
            "POST",
            "/api/v1/access/sessions",
            body={"login_identifier": "owner@example.com", "password": _PASSWORD},
            headers={"origin": _ORIGIN, "x-correlation-id": "login-request"},
        )
        assert login.status == 201
        assert login.json()["active_tenant_id"] == bootstrap.tenant_id.value
        assert login.json()["tenant_selection_required"] is False
        assert login.header("x-correlation-id") == "login-request"
        assert login.header("x-content-type-options") == "nosniff"
        assert login.header("x-frame-options") == "DENY"
        set_cookie = login.headers_for("set-cookie")
        assert any("evidentia_auth=" in item and "HttpOnly" in item for item in set_cookie)
        assert any("evidentia_auth=" in item and "Path=/api/v1" in item for item in set_cookie)
        assert any("evidentia_csrf=" in item and "Path=/" in item for item in set_cookie)
        assert all("SameSite=lax" in item for item in set_cookie)

        cookies = _cookies(login)
        cookie_header = _cookie_header(cookies)
        context = await _request(
            app,
            "GET",
            "/api/v1/access/context",
            headers={
                "cookie": cookie_header,
                "x-correlation-id": "context-request",
                "x-operator-id": "attacker-controlled",
                "x-tenant-id": "attacker-controlled",
            },
        )
        assert context.status == 200
        assert context.json()["operator_id"] == bootstrap.operator_id.value
        assert context.json()["tenant_id"] == bootstrap.tenant_id.value
        assert context.json()["correlation_id"] == "context-request"
        assert "schemas.publish" in context.json()["capabilities"]

        missing_csrf = await _request(
            app,
            "PUT",
            "/api/v1/access/session/tenant",
            body={"tenant_id": bootstrap.tenant_id.value},
            headers={"origin": _ORIGIN, "cookie": cookie_header},
        )
        assert missing_csrf.status == 403
        assert missing_csrf.json()["code"] == "csrf_rejected"

        selected = await _request(
            app,
            "PUT",
            "/api/v1/access/session/tenant",
            body={"tenant_id": bootstrap.tenant_id.value},
            headers={
                "origin": _ORIGIN,
                "cookie": cookie_header,
                "x-csrf-token": cookies["evidentia_csrf"],
            },
        )
        assert selected.status == 200
        rotated_cookies = _cookies(selected)
        assert rotated_cookies["evidentia_auth"] != cookies["evidentia_auth"]

        reused = await _request(
            app,
            "GET",
            "/api/v1/access/context",
            headers={"cookie": cookie_header},
        )
        assert reused.status == 401
        assert reused.json()["code"] == "session_invalid"

        logout = await _request(
            app,
            "DELETE",
            "/api/v1/access/session",
            headers={
                "origin": _ORIGIN,
                "cookie": _cookie_header(rotated_cookies),
                "x-csrf-token": rotated_cookies["evidentia_csrf"],
            },
        )
        assert logout.status == 204
        assert all("Max-Age=0" in item for item in logout.headers_for("set-cookie"))
    finally:
        await app.state.access_runtime.close()


def test_browser_session_and_trusted_context_api(
    disposable_postgres_database: DisposablePostgresDatabase,
) -> None:
    """Prove real login, context, tenant rotation, CSRF, and logout behavior.

    @skyhook-implements REQ-012
    @skyhook-implements NFR-006
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    asyncio.run(_exercise_access_api(disposable_postgres_database))
