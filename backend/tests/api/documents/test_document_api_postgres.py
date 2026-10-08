"""Authenticated document upload and status proof against disposable PostgreSQL.

@skyhook-implements REQ-001
@skyhook-implements REQ-012
@skyhook-implements REQ-015
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import MutableMapping
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import pytest
from backend.tests.integration.support import DisposablePostgresDatabase
from fastapi import FastAPI
from pydantic import SecretStr

from evidentia.config.settings import (
    ApiSettings,
    IdentitySettings,
    SessionSettings,
    StorageSettings,
)
from evidentia.entrypoints.api import create_app
from evidentia.entrypoints.api.documents import DocumentApiRuntime
from evidentia.entrypoints.cli.identity import bootstrap_configured_identity

pytestmark = pytest.mark.postgres
_PASSWORD = "document-api-unique-password"
_ORIGIN = "http://localhost:3000"
_BOUNDARY = "evidentia-document-boundary"
_CONTENT = b"%PDF-1.7\ninvoice fixture\n%%EOF\n"


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def json(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(self.body))


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> _Response:
    target = urlsplit(path)
    request_headers = {"host": "testserver", **(headers or {})}
    scope: MutableMapping[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": target.path,
        "raw_path": target.path.encode(),
        "query_string": target.query.encode(),
        "root_path": "",
        "headers": [
            (key.lower().encode(), value.encode()) for key, value in request_headers.items()
        ],
        "client": ("127.0.0.1", 43210),
        "server": ("testserver", 80),
    }
    sent = False
    messages: list[MutableMapping[str, Any]] = []

    async def receive() -> MutableMapping[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body" and isinstance(message.get("body", b""), bytes)
    )
    raw_headers = start.get("headers", [])
    if not isinstance(raw_headers, list):
        raise TypeError("ASGI response headers must be a list")
    return _Response(
        int(start["status"]),
        tuple((key.decode(), value.decode()) for key, value in raw_headers),
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


def _multipart(
    filename: str,
    content: bytes,
    *,
    media_type: str = "application/pdf",
) -> bytes:
    return (
        (
            f"--{_BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
            f"Content-Type: {media_type}\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{_BOUNDARY}--\r\n".encode()
    )


async def _exercise_upload(database: DisposablePostgresDatabase, artifact_root: Path) -> None:
    settings = ApiSettings(
        database=database.settings,
        identity=IdentitySettings(
            bootstrap_login_identifier="document-owner@example.com",
            bootstrap_display_name="Document Owner",
            bootstrap_tenant_slug="document-team",
            bootstrap_tenant_name="Document Team",
            bootstrap_password=SecretStr(_PASSWORD),
        ),
        session=SessionSettings(
            secret=SecretStr("0123456789abcdef0123456789abcdef"),
            cookie_name="evidentia_auth",
        ),
        storage=StorageSettings(root=artifact_root, maximum_upload_bytes=1024),
    )
    await bootstrap_configured_identity(settings)
    document_runtime = DocumentApiRuntime(settings, artifact_root=artifact_root)
    app = create_app(settings, document_runtime=document_runtime)
    try:
        login = await _request(
            app,
            "POST",
            "/api/v1/access/sessions",
            body=json.dumps(
                {"login_identifier": "document-owner@example.com", "password": _PASSWORD}
            ).encode(),
            headers={"origin": _ORIGIN, "content-type": "application/json"},
        )
        assert login.status == 201
        browser = _browser_headers(login)

        missing_csrf_headers = dict(browser)
        missing_csrf_headers.pop("x-csrf-token")
        missing_csrf = await _request(
            app,
            "POST",
            "/api/v1/documents",
            body=_multipart("invoice.pdf", _CONTENT),
            headers={
                **missing_csrf_headers,
                "content-type": f"multipart/form-data; boundary={_BOUNDARY}",
                "idempotency-key": "document-upload-1",
            },
        )
        assert missing_csrf.status == 403
        assert missing_csrf.json()["code"] == "csrf_rejected"

        upload_headers = {
            **browser,
            "content-type": f"multipart/form-data; boundary={_BOUNDARY}",
            "idempotency-key": "document-upload-1",
        }
        uploaded = await _request(
            app,
            "POST",
            "/api/v1/documents",
            body=_multipart("invoice.pdf", _CONTENT),
            headers=upload_headers,
        )
        assert uploaded.status == 201
        receipt = uploaded.json()
        assert receipt["status"] == "preserved"
        assert receipt["original_filename"] == "invoice.pdf"
        assert receipt["content_sha256"] is not None
        document_id = str(receipt["document_id"])
        assert dict(uploaded.headers)["x-content-type-options"] == "nosniff"

        repeated = await _request(
            app,
            "POST",
            "/api/v1/documents",
            body=_multipart("invoice.pdf", _CONTENT),
            headers=upload_headers,
        )
        assert repeated.status == 201
        assert repeated.json() == receipt

        changed = await _request(
            app,
            "POST",
            "/api/v1/documents",
            body=_multipart("invoice.pdf", b"changed source bytes"),
            headers=upload_headers,
        )
        assert changed.status == 409
        assert changed.json()["code"] == "idempotency_key_reused"

        too_large = await _request(
            app,
            "POST",
            "/api/v1/documents",
            body=_multipart("oversized.pdf", b"x" * 1025),
            headers={**upload_headers, "idempotency-key": "document-too-large"},
        )
        assert too_large.status == 413

        unsupported = await _request(
            app,
            "POST",
            "/api/v1/documents",
            body=_multipart(
                "webpage.html", b"<script>not executed</script>", media_type="text/html"
            ),
            headers={**upload_headers, "idempotency-key": "document-unsupported"},
        )
        assert unsupported.status == 415

        unsafe_filename = await _request(
            app,
            "POST",
            "/api/v1/documents",
            body=_multipart("../outside.pdf", _CONTENT),
            headers={**upload_headers, "idempotency-key": "document-unsafe-name"},
        )
        assert unsafe_filename.status == 400

        scan_bytes = b"\x89PNG\r\nopaque scan fixture"
        scan = await _request(
            app,
            "POST",
            "/api/v1/documents",
            body=_multipart("scan.png", scan_bytes, media_type="image/png"),
            headers={**upload_headers, "idempotency-key": "document-scan-1"},
        )
        assert scan.status == 201
        assert scan.json()["media_type"] == "image/png"
        assert scan.json()["status"] == "preserved"

        status = await _request(
            app,
            "GET",
            f"/api/v1/documents/{document_id}",
            headers={key: value for key, value in browser.items() if key != "x-csrf-token"},
        )
        assert status.status == 200
        assert status.json() == receipt

        stored = list(artifact_root.glob("**/*"))
        files = [path for path in stored if path.is_file()]
        assert len(files) == 2
        assert _CONTENT in [path.read_bytes() for path in files]
        assert scan_bytes in [path.read_bytes() for path in files]
        assert all(document_id not in str(path) for path in files)

        # Rebuild the API composition root and all database runtimes to model
        # an application restart while retaining only the database and bytes.
        await app.state.access_runtime.close()
        await app.state.schema_runtime.close()
        await app.state.document_runtime.close()
        app = create_app(
            settings,
            document_runtime=DocumentApiRuntime(settings, artifact_root=artifact_root),
        )
        after_restart = await _request(
            app,
            "GET",
            f"/api/v1/documents/{document_id}",
            headers={key: value for key, value in browser.items() if key != "x-csrf-token"},
        )
        assert after_restart.status == 200
        assert after_restart.json() == receipt
        assert files[0].read_bytes() == _CONTENT
    finally:
        await app.state.access_runtime.close()
        await app.state.schema_runtime.close()
        await document_runtime.close()


def test_authenticated_upload_and_custody_status(
    disposable_postgres_database: DisposablePostgresDatabase,
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_upload(disposable_postgres_database, tmp_path / "artifacts"))
