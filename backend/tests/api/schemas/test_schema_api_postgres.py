"""Authenticated schema lifecycle proof against disposable native PostgreSQL.

@skyhook-implements REQ-003
@skyhook-implements REQ-012
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements NFR-008
@skyhook-story X51S43NTMRW5ASYSKJBF7FW845
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

_PASSWORD = "schema-api-unique-password"
_ORIGIN = "http://localhost:3000"


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def json(self) -> dict[str, Any]:
        return json.loads(self.body)


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> _Response:
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
    sent = False
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )
    return _Response(
        start["status"],
        tuple((key.decode(), value.decode()) for key, value in start["headers"]),
        response_body,
    )


def _browser_headers(login: _Response) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for key, value in login.headers:
        if key == "set-cookie":
            parsed = SimpleCookie()
            parsed.load(value)
            cookies.update({name: morsel.value for name, morsel in parsed.items()})
    return {
        "origin": _ORIGIN,
        "cookie": "; ".join(f"{key}={value}" for key, value in cookies.items()),
        "x-csrf-token": cookies["evidentia_csrf"],
    }


async def _exercise_schema_api(database: DisposablePostgresDatabase) -> None:
    settings = ApiSettings(
        database=database.settings,
        identity=IdentitySettings(
            bootstrap_login_identifier="schema-owner@example.com",
            bootstrap_display_name="Schema Owner",
            bootstrap_tenant_slug="schema-team",
            bootstrap_tenant_name="Schema Team",
            bootstrap_password=_PASSWORD,
        ),
        session=SessionSettings(
            secret="0123456789abcdef0123456789abcdef",
            cookie_name="evidentia_auth",
        ),
    )
    await bootstrap_configured_identity(settings)
    app = create_app(settings)
    try:
        login = await _request(
            app,
            "POST",
            "/api/v1/access/sessions",
            body={"login_identifier": "schema-owner@example.com", "password": _PASSWORD},
            headers={"origin": _ORIGIN},
        )
        assert login.status == 201
        browser = _browser_headers(login)
        payload: dict[str, object] = {
            "content": {
                "artifacts": [],
                "fields": [
                    {
                        "key": "title",
                        "cardinality": {"minimum": 0, "maximum": 1},
                        "artifacts": [],
                        "value": {
                            "type": {
                                "kind": "string",
                                "min_length": 0,
                                "max_length": None,
                                "pattern": None,
                            },
                            "artifacts": [],
                        },
                    }
                ],
                "modules": [],
            }
        }

        missing_csrf = await _request(
            app,
            "POST",
            "/api/v1/schemas/drafts",
            body=payload,
            headers={
                "cookie": browser["cookie"],
                "idempotency-key": "create-1",
                "origin": _ORIGIN,
            },
        )
        assert missing_csrf.status == 403
        assert missing_csrf.json()["code"] == "csrf_rejected"

        command_headers = {**browser, "idempotency-key": "create-1"}
        created = await _request(
            app, "POST", "/api/v1/schemas/drafts", body=payload, headers=command_headers
        )
        assert created.status == 201
        assert created.json()["revision"] == 1
        schema_id = created.json()["schema_id"]

        replayed = await _request(
            app, "POST", "/api/v1/schemas/drafts", body=payload, headers=command_headers
        )
        assert replayed.status == 201
        assert replayed.json() == created.json()

        reused = await _request(
            app,
            "POST",
            "/api/v1/schemas/drafts",
            body={"content": {"releaseLabel": "different"}},
            headers=command_headers,
        )
        assert reused.status == 409
        assert reused.json()["code"] == "idempotency_key_reused"

        listed = await _request(
            app,
            "GET",
            "/api/v1/schemas/drafts",
            headers={"cookie": browser["cookie"], "x-tenant-id": "untrusted"},
        )
        assert listed.status == 200
        assert [item["schema_id"] for item in listed.json()["items"]] == [schema_id]

        replaced = await _request(
            app,
            "PUT",
            f"/api/v1/schemas/drafts/{schema_id}",
            body={"expected_revision": 1, **payload},
            headers={**browser, "idempotency-key": "replace-1"},
        )
        assert replaced.status == 200
        assert replaced.json()["revision"] == 2

        stale = await _request(
            app,
            "PUT",
            f"/api/v1/schemas/drafts/{schema_id}",
            body={"expected_revision": 1, **payload},
            headers={**browser, "idempotency-key": "replace-stale"},
        )
        assert stale.status == 409
        assert stale.json()["code"] == "schema_revision_conflict"

        published = await _request(
            app,
            "POST",
            f"/api/v1/schemas/drafts/{schema_id}/publications",
            body={"expected_revision": 2},
            headers={**browser, "idempotency-key": "publish-1"},
        )
        assert published.status == 201
        assert published.json()["publication"]["version"] == 1
        assert published.json()["next_draft"]["revision"] == 3

        publication = await _request(
            app,
            "GET",
            f"/api/v1/schemas/{schema_id}/versions/1",
            headers={"cookie": browser["cookie"]},
        )
        assert publication.status == 200
        assert (
            publication.json()["content_sha256"]
            == published.json()["publication"]["content_sha256"]
        )
    finally:
        await app.state.access_runtime.close()
        await app.state.schema_runtime.close()


def test_schema_api_lifecycle_is_authorized_atomic_and_retry_safe(
    disposable_postgres_database: DisposablePostgresDatabase,
) -> None:
    """Exercise the browser-visible lifecycle, conflicts, and safe retries."""
    asyncio.run(_exercise_schema_api(disposable_postgres_database))
