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
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from backend.tests.integration.support import DisposablePostgresDatabase
from fastapi import FastAPI
from sqlalchemy import insert

from evidentia.config.settings import ApiSettings, IdentitySettings, SessionSettings
from evidentia.entrypoints.api import create_app
from evidentia.entrypoints.cli.identity import bootstrap_configured_identity
from evidentia.modules.access.infrastructure.persistence import (
    MembershipCapabilityRecord,
    MembershipRecord,
    TenantRecord,
)

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

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        return next((value for key, value in self.headers if key == lowered), None)


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> _Response:
    target = urlsplit(path)
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
    bootstrap = await bootstrap_configured_identity(settings)
    app = create_app(settings)
    response_bodies: list[bytes] = []
    try:
        login = await _request(
            app,
            "POST",
            "/api/v1/access/sessions",
            body={"login_identifier": "schema-owner@example.com", "password": _PASSWORD},
            headers={"origin": _ORIGIN},
        )
        assert login.status == 201
        response_bodies.append(login.body)
        browser = _browser_headers(login)
        content: dict[str, object] = {
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
        payload: dict[str, object] = {"content": content}

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
        response_bodies.append(missing_csrf.body)

        unauthenticated = await _request(app, "GET", "/api/v1/schemas/drafts")
        assert unauthenticated.status == 401
        assert unauthenticated.json()["code"] == "session_required"
        response_bodies.append(unauthenticated.body)

        invalid = await _request(
            app,
            "POST",
            "/api/v1/schemas/drafts",
            body={
                "content": {
                    "fields": [
                        {
                            "key": "unknown",
                            "cardinality": {"minimum": 0, "maximum": 1},
                            "artifacts": [],
                            "value": {
                                "type": {"kind": "future_core"},
                                "artifacts": [],
                            },
                        }
                    ]
                }
            },
            headers={**browser, "idempotency-key": "invalid-1"},
        )
        assert invalid.status == 400
        assert invalid.json()["code"] == "invalid_schema_definition"
        response_bodies.append(invalid.body)

        command_headers = {**browser, "idempotency-key": "create-1"}
        created, concurrent_replay = await asyncio.gather(
            _request(
                app,
                "POST",
                "/api/v1/schemas/drafts",
                body=payload,
                headers={**command_headers, "x-correlation-id": "create-primary"},
            ),
            _request(
                app,
                "POST",
                "/api/v1/schemas/drafts",
                body=payload,
                headers={**command_headers, "x-correlation-id": "create-concurrent"},
            ),
        )
        assert created.status == 201
        assert concurrent_replay.status == 201
        assert concurrent_replay.json() == created.json()
        assert created.json()["revision"] == 1
        schema_id = created.json()["schema_id"]
        response_bodies.extend((created.body, concurrent_replay.body))

        replayed = await _request(
            app, "POST", "/api/v1/schemas/drafts", body=payload, headers=command_headers
        )
        assert replayed.status == 201
        assert replayed.json() == created.json()
        response_bodies.append(replayed.body)

        reused = await _request(
            app,
            "POST",
            "/api/v1/schemas/drafts",
            body={"content": {"releaseLabel": "different"}},
            headers=command_headers,
        )
        assert reused.status == 409
        assert reused.json()["code"] == "idempotency_key_reused"
        response_bodies.append(reused.body)

        second = await _request(
            app,
            "POST",
            "/api/v1/schemas/drafts",
            body=payload,
            headers={**browser, "idempotency-key": "create-2"},
        )
        assert second.status == 201
        first_page = await _request(
            app,
            "GET",
            "/api/v1/schemas/drafts?limit=1",
            headers={"cookie": browser["cookie"], "x-tenant-id": "untrusted"},
        )
        assert first_page.status == 200
        assert len(first_page.json()["items"]) == 1
        assert first_page.json()["next_cursor"] is not None
        second_page = await _request(
            app,
            "GET",
            f"/api/v1/schemas/drafts?limit=1&cursor={first_page.json()['next_cursor']}",
            headers={"cookie": browser["cookie"]},
        )
        assert second_page.status == 200
        assert len(second_page.json()["items"]) == 1
        assert second_page.json()["next_cursor"] is None
        assert {
            first_page.json()["items"][0]["schema_id"],
            second_page.json()["items"][0]["schema_id"],
        } == {schema_id, second.json()["schema_id"]}
        response_bodies.extend((second.body, first_page.body, second_page.body))

        replacements = await asyncio.gather(
            _request(
                app,
                "PUT",
                f"/api/v1/schemas/drafts/{schema_id}",
                body={"expected_revision": 1, **payload},
                headers={**browser, "idempotency-key": "replace-concurrent-1"},
            ),
            _request(
                app,
                "PUT",
                f"/api/v1/schemas/drafts/{schema_id}",
                body={"expected_revision": 1, **payload},
                headers={**browser, "idempotency-key": "replace-concurrent-2"},
            ),
        )
        assert sorted(response.status for response in replacements) == [200, 409]
        replaced = next(response for response in replacements if response.status == 200)
        assert replaced.json()["revision"] == 2
        conflict = next(response for response in replacements if response.status == 409)
        assert conflict.json()["code"] == "schema_revision_conflict"
        response_bodies.extend(response.body for response in replacements)

        stale = await _request(
            app,
            "PUT",
            f"/api/v1/schemas/drafts/{schema_id}",
            body={"expected_revision": 1, **payload},
            headers={**browser, "idempotency-key": "replace-stale"},
        )
        assert stale.status == 409
        assert stale.json()["code"] == "schema_revision_conflict"
        response_bodies.append(stale.body)

        published = await _request(
            app,
            "POST",
            f"/api/v1/schemas/drafts/{schema_id}/publications",
            body={"expected_revision": 2},
            headers={
                **browser,
                "idempotency-key": "publish-1",
                "x-correlation-id": "publish-original",
            },
        )
        assert published.status == 201
        assert published.header("x-correlation-id") == "publish-original"
        assert published.json()["publication"]["version"] == 1
        assert published.json()["next_draft"]["revision"] == 3
        assert published.json()["publication"]["correlation_id"] == "publish-original"
        response_bodies.append(published.body)

        await app.state.access_runtime.close()
        await app.state.schema_runtime.close()
        app = create_app(settings)

        restarted_replay = await _request(
            app,
            "POST",
            f"/api/v1/schemas/drafts/{schema_id}/publications",
            body={"expected_revision": 2},
            headers={
                **browser,
                "idempotency-key": "publish-1",
                "x-correlation-id": "publish-after-restart",
            },
        )
        assert restarted_replay.status == 201
        assert restarted_replay.json() == published.json()
        assert restarted_replay.header("x-correlation-id") == "publish-after-restart"
        response_bodies.append(restarted_replay.body)

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
        response_bodies.append(publication.body)

        changed_draft = await _request(
            app,
            "PUT",
            f"/api/v1/schemas/drafts/{schema_id}",
            body={
                "expected_revision": 3,
                "content": {**content, "releaseLabel": "next-version"},
            },
            headers={**browser, "idempotency-key": "replace-after-publication"},
        )
        assert changed_draft.status == 200
        unchanged_publication = await _request(
            app,
            "GET",
            f"/api/v1/schemas/{schema_id}/versions/1",
            headers={"cookie": browser["cookie"]},
        )
        assert unchanged_publication.json() == publication.json()
        response_bodies.extend((changed_draft.body, unchanged_publication.body))

        exported_draft = await _request(
            app,
            "GET",
            f"/api/v1/schemas/drafts/{schema_id}/package",
            headers={"cookie": browser["cookie"]},
        )
        assert exported_draft.status == 200
        assert exported_draft.json()["format"] == "evidentia.schema-draft"
        assert exported_draft.json()["schema"]["id"] == schema_id
        invalid_package = await _request(
            app,
            "POST",
            "/api/v1/schemas/imports/preview",
            body={"package": {"format": "vendor.schema", "version": 1}},
            headers=browser,
        )
        assert invalid_package.status == 400
        assert invalid_package.json()["code"] == "invalid_schema_package"
        oversized_package = await _request(
            app,
            "POST",
            "/api/v1/schemas/imports/preview",
            body={"package": {"padding": "x" * 1_048_576}},
            headers=browser,
        )
        assert oversized_package.status == 400
        assert oversized_package.json()["code"] == "schema_package_too_large"
        imported_package = json.loads(json.dumps(exported_draft.json()))
        imported_package["schema"]["fields"].append(
            {
                "key": "approval_code",
                "cardinality": {"minimum": 1, "maximum": 1},
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
        )
        previewed_import = await _request(
            app,
            "POST",
            "/api/v1/schemas/imports/preview",
            body={"package": imported_package, "target_schema_id": schema_id},
            headers=browser,
        )
        assert previewed_import.status == 200
        assert previewed_import.json()["compatibility"]["level"] == "breaking"
        assert previewed_import.json()["target_revision"] == 4
        assert previewed_import.json()["canonical_sha256"]

        import_command = {
            "package": imported_package,
            "target_schema_id": schema_id,
            "expected_revision": 4,
        }
        applied_import = await _request(
            app,
            "POST",
            "/api/v1/schemas/imports",
            body=import_command,
            headers={**browser, "idempotency-key": "apply-import-1"},
        )
        assert applied_import.status == 201
        assert applied_import.json()["created"] is False
        assert applied_import.json()["draft"]["schema_id"] == schema_id
        assert applied_import.json()["draft"]["revision"] == 5
        replayed_import = await _request(
            app,
            "POST",
            "/api/v1/schemas/imports",
            body=import_command,
            headers={**browser, "idempotency-key": "apply-import-1"},
        )
        assert replayed_import.status == 201
        assert replayed_import.json() == applied_import.json()
        stale_import = await _request(
            app,
            "POST",
            "/api/v1/schemas/imports",
            body=import_command,
            headers={**browser, "idempotency-key": "apply-import-stale"},
        )
        assert stale_import.status == 409
        assert stale_import.json()["code"] == "schema_revision_conflict"

        created_from_import = await _request(
            app,
            "POST",
            "/api/v1/schemas/imports",
            body={"package": imported_package},
            headers={**browser, "idempotency-key": "apply-import-new"},
        )
        assert created_from_import.status == 201
        assert created_from_import.json()["created"] is True
        assert created_from_import.json()["draft"]["schema_id"] != schema_id
        assert created_from_import.json()["draft"]["revision"] == 1

        exported_publication = await _request(
            app,
            "GET",
            f"/api/v1/schemas/{schema_id}/versions/1/package",
            headers={"cookie": browser["cookie"]},
        )
        assert exported_publication.status == 200
        assert exported_publication.json() == publication.json()["snapshot"]
        await app.state.access_runtime.close()
        await app.state.schema_runtime.close()
        app = create_app(settings)
        restarted_import_replay = await _request(
            app,
            "POST",
            "/api/v1/schemas/imports",
            body=import_command,
            headers={**browser, "idempotency-key": "apply-import-1"},
        )
        assert restarted_import_replay.status == 201
        assert restarted_import_replay.json() == applied_import.json()
        response_bodies.extend(
            (
                exported_draft.body,
                invalid_package.body,
                oversized_package.body,
                previewed_import.body,
                applied_import.body,
                replayed_import.body,
                stale_import.body,
                created_from_import.body,
                exported_publication.body,
                restarted_import_replay.body,
            )
        )

        isolated_tenant_id = uuid4()
        isolated_membership_id = uuid4()
        async with app.state.access_runtime.engine.begin() as connection:
            await connection.execute(
                insert(TenantRecord).values(
                    tenant_id=isolated_tenant_id,
                    slug="read-only-team",
                    display_name="Read-only Team",
                    status="active",
                )
            )
            await connection.execute(
                insert(MembershipRecord).values(
                    membership_id=isolated_membership_id,
                    tenant_id=isolated_tenant_id,
                    operator_id=UUID(bootstrap.operator_id.value),
                    status="active",
                )
            )
            await connection.execute(
                insert(MembershipCapabilityRecord).values(
                    membership_id=isolated_membership_id,
                    capability="schemas.read",
                )
            )

        selected_isolated = await _request(
            app,
            "PUT",
            "/api/v1/access/session/tenant",
            body={"tenant_id": str(isolated_tenant_id)},
            headers=browser,
        )
        assert selected_isolated.status == 200
        isolated_browser = _browser_headers(selected_isolated)
        isolated_get = await _request(
            app,
            "GET",
            f"/api/v1/schemas/drafts/{schema_id}",
            headers={"cookie": isolated_browser["cookie"]},
        )
        assert isolated_get.status == 404
        isolated_create = await _request(
            app,
            "POST",
            "/api/v1/schemas/drafts",
            body=payload,
            headers={**isolated_browser, "idempotency-key": "isolated-create"},
        )
        assert isolated_create.status == 403
        assert isolated_create.json()["code"] == "access_denied"
        isolated_preview = await _request(
            app,
            "POST",
            "/api/v1/schemas/imports/preview",
            body={"package": imported_package, "target_schema_id": schema_id},
            headers=isolated_browser,
        )
        assert isolated_preview.status == 404
        isolated_apply = await _request(
            app,
            "POST",
            "/api/v1/schemas/imports",
            body={"package": imported_package},
            headers={**isolated_browser, "idempotency-key": "isolated-import"},
        )
        assert isolated_apply.status == 403
        assert isolated_apply.json()["code"] == "access_denied"
        response_bodies.extend(
            (
                selected_isolated.body,
                isolated_get.body,
                isolated_create.body,
                isolated_preview.body,
                isolated_apply.body,
            )
        )

        recovered = await _request(
            app,
            "PUT",
            "/api/v1/access/session/tenant",
            body={"tenant_id": bootstrap.tenant_id.value},
            headers=isolated_browser,
        )
        assert recovered.status == 200
        recovered_browser = _browser_headers(recovered)
        recovered_get = await _request(
            app,
            "GET",
            f"/api/v1/schemas/{schema_id}/versions/1",
            headers={"cookie": recovered_browser["cookie"]},
        )
        assert recovered_get.status == 200
        assert recovered_get.json() == publication.json()
        response_bodies.extend((recovered.body, recovered_get.body))

        combined_bodies = b"".join(response_bodies)
        assert _PASSWORD.encode() not in combined_bodies
        assert b"evidentia_auth" not in combined_bodies
        assert b"evidentia_csrf" not in combined_bodies
    finally:
        await app.state.access_runtime.close()
        await app.state.schema_runtime.close()


def test_schema_api_lifecycle_is_authorized_atomic_and_retry_safe(
    disposable_postgres_database: DisposablePostgresDatabase,
) -> None:
    """Exercise the browser-visible lifecycle, conflicts, and safe retries."""
    asyncio.run(_exercise_schema_api(disposable_postgres_database))
