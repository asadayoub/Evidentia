"""Browser-level access API proof against disposable native PostgreSQL.

@skyhook-implements REQ-012
@skyhook-implements NFR-006
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import Any

import pytest
from backend.tests.integration.support import DisposablePostgresDatabase
from fastapi import FastAPI
from sqlalchemy import select, update

from evidentia.config.settings import ApiSettings, IdentitySettings, SessionSettings
from evidentia.entrypoints.api import create_app
from evidentia.entrypoints.cli.identity import bootstrap_configured_identity
from evidentia.modules.access.infrastructure.persistence import (
    AccessSessionRecord,
    LocalPasswordCredentialRecord,
)
from evidentia.modules.access.infrastructure.tokens import SecureSessionTokenProvider
from evidentia.modules.access.public import OpaqueSessionToken, TenantId

pytestmark = pytest.mark.postgres

_PASSWORD = "a-unique-api-password"
_ORIGIN = "http://localhost:3000"


class _SecurityEventCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


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
    security_logger = logging.getLogger("evidentia.api.security")
    original_handlers = security_logger.handlers[:]
    original_level = security_logger.level
    original_propagate = security_logger.propagate
    capture = _SecurityEventCapture()
    security_logger.handlers = [capture]
    security_logger.setLevel(logging.INFO)
    security_logger.propagate = False
    app: FastAPI | None = None
    response_bodies: list[bytes] = []
    raw_tokens: list[str] = []
    try:
        bootstrap = await bootstrap_configured_identity(settings)
        app = create_app(settings)
        rejected_origin = await _request(
            app,
            "POST",
            "/api/v1/access/sessions",
            body={"login_identifier": "owner@example.com", "password": _PASSWORD},
            headers={"origin": "https://attacker.example"},
        )
        assert rejected_origin.status == 403
        assert rejected_origin.json()["code"] == "origin_rejected"
        response_bodies.append(rejected_origin.body)

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
        raw_tokens.append(cookies["evidentia_auth"])
        cookie_header = _cookie_header(cookies)
        response_bodies.append(login.body)
        restored_session = await _request(
            app,
            "GET",
            "/api/v1/access/session",
            headers={
                "cookie": cookie_header,
                "x-correlation-id": "session-restore-request",
            },
        )
        assert restored_session.status == 200
        assert restored_session.json()["operator_id"] == bootstrap.operator_id.value
        assert restored_session.json()["active_tenant_id"] == bootstrap.tenant_id.value
        assert restored_session.json()["available_tenants"] == [
            {
                "tenant_id": bootstrap.tenant_id.value,
                "slug": "review-team",
                "display_name": "Review Team",
            }
        ]
        response_bodies.append(restored_session.body)
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
        response_bodies.append(context.body)

        await app.state.access_runtime.close()
        app = create_app(settings)
        after_restart = await _request(
            app,
            "GET",
            "/api/v1/access/context",
            headers={"cookie": cookie_header, "x-correlation-id": "restart-request"},
        )
        assert after_restart.status == 200
        assert after_restart.json()["session_id"] == context.json()["session_id"]
        response_bodies.append(after_restart.body)

        unavailable_tenant = TenantId.new()
        cross_tenant = await _request(
            app,
            "PUT",
            "/api/v1/access/session/tenant",
            body={"tenant_id": unavailable_tenant.value},
            headers={
                "origin": _ORIGIN,
                "cookie": cookie_header,
                "x-csrf-token": cookies["evidentia_csrf"],
                "x-correlation-id": "cross-tenant-request",
            },
        )
        assert cross_tenant.status == 403
        assert cross_tenant.json()["code"] == "tenant_not_available"
        response_bodies.append(cross_tenant.body)

        missing_csrf = await _request(
            app,
            "PUT",
            "/api/v1/access/session/tenant",
            body={"tenant_id": bootstrap.tenant_id.value},
            headers={"origin": _ORIGIN, "cookie": cookie_header},
        )
        assert missing_csrf.status == 403
        assert missing_csrf.json()["code"] == "csrf_rejected"
        response_bodies.append(missing_csrf.body)

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
        raw_tokens.append(rotated_cookies["evidentia_auth"])
        response_bodies.append(selected.body)

        reused = await _request(
            app,
            "GET",
            "/api/v1/access/context",
            headers={"cookie": cookie_header},
        )
        assert reused.status == 401
        assert reused.json()["code"] == "session_invalid"
        response_bodies.append(reused.body)

        expiring_login = await _request(
            app,
            "POST",
            "/api/v1/access/sessions",
            body={"login_identifier": "owner@example.com", "password": _PASSWORD},
            headers={"origin": _ORIGIN, "x-correlation-id": "expiry-login"},
        )
        assert expiring_login.status == 201
        expiring_cookies = _cookies(expiring_login)
        expiring_raw_token = expiring_cookies["evidentia_auth"]
        raw_tokens.append(expiring_raw_token)
        digest = SecureSessionTokenProvider().digest(OpaqueSessionToken(expiring_raw_token))
        expired_now = datetime.now(UTC)
        async with app.state.access_runtime.engine.begin() as connection:
            await connection.execute(
                update(AccessSessionRecord)
                .where(AccessSessionRecord.token_sha256 == digest.value)
                .values(
                    authenticated_at=expired_now - timedelta(minutes=20),
                    last_seen_at=expired_now - timedelta(minutes=16),
                    expires_at=expired_now - timedelta(minutes=15),
                )
            )
        expired = await _request(
            app,
            "GET",
            "/api/v1/access/context",
            headers={
                "cookie": _cookie_header(expiring_cookies),
                "x-correlation-id": "expired-request",
            },
        )
        assert expired.status == 401
        assert expired.json()["code"] == "session_invalid"
        response_bodies.extend((expiring_login.body, expired.body))

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
        response_bodies.append(logout.body)

        await app.state.access_runtime.close()
        app = create_app(settings)
        after_logout_restart = await _request(
            app,
            "GET",
            "/api/v1/access/context",
            headers={"cookie": _cookie_header(rotated_cookies)},
        )
        assert after_logout_restart.status == 401
        response_bodies.append(after_logout_restart.body)

        bad_password = "deliberately-wrong-password"
        denied_login = await _request(
            app,
            "POST",
            "/api/v1/access/sessions",
            body={"login_identifier": "owner@example.com", "password": bad_password},
            headers={"origin": _ORIGIN, "x-correlation-id": "denied-login"},
        )
        assert denied_login.status in {401, 429}
        assert denied_login.json()["code"] == "authentication_failed"
        response_bodies.append(denied_login.body)

        async with app.state.access_runtime.engine.connect() as connection:
            persisted_tokens = (
                await connection.execute(select(AccessSessionRecord.token_sha256))
            ).scalars()
            password_hashes = (
                await connection.execute(select(LocalPasswordCredentialRecord.password_hash))
            ).scalars()
            persisted_token_values = tuple(str(value) for value in persisted_tokens)
            password_hash_values = tuple(str(value) for value in password_hashes)

        assert persisted_token_values
        assert all(len(value) == 64 for value in persisted_token_values)
        serialized_responses = b"".join(response_bodies).decode(errors="replace")
        serialized_events = json.dumps(
            [record.__dict__ for record in capture.records],
            default=str,
            sort_keys=True,
        )
        for secret in (_PASSWORD, bad_password, *raw_tokens):
            assert secret not in serialized_responses
            assert secret not in serialized_events
            assert all(secret not in value for value in persisted_token_values)
            assert all(secret not in value for value in password_hash_values)

        event_names = {str(record.__dict__.get("security_event")) for record in capture.records}
        assert {
            "identity.bootstrap.succeeded",
            "access.origin.denied",
            "access.login.succeeded",
            "access.login.denied",
            "access.tenant_selection.denied",
            "access.tenant_selection.succeeded",
            "access.context.denied",
            "access.logout.succeeded",
        } <= event_names
        attributed = [
            record
            for record in capture.records
            if record.__dict__.get("security_event")
            in {
                "access.login.succeeded",
                "access.tenant_selection.succeeded",
                "access.logout.succeeded",
            }
        ]
        assert attributed
        assert all(record.__dict__.get("operator_id") for record in attributed)
        assert all(record.__dict__.get("session_id") for record in attributed)
    finally:
        if app is not None:
            await app.state.access_runtime.close()
        security_logger.handlers = original_handlers
        security_logger.setLevel(original_level)
        security_logger.propagate = original_propagate


def test_browser_session_and_trusted_context_api(
    disposable_postgres_database: DisposablePostgresDatabase,
) -> None:
    """Prove real login, context, tenant rotation, CSRF, and logout behavior.

    @skyhook-implements REQ-012
    @skyhook-implements NFR-006
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    asyncio.run(_exercise_access_api(disposable_postgres_database))
