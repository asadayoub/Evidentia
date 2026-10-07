# Evidentia TypeScript SDK

The SDK is the supported TypeScript boundary for Evidentia's versioned HTTP API. Its route, request, response, and error types are generated from `contracts/openapi/evidentia.openapi.json`; React-specific query and routing behavior belongs in `frontend`.

## Access interaction contract

- Authentication uses an opaque server-owned session cookie. Application code cannot read, persist, or forward the bearer value.
- Every request includes browser credentials and a correlation identifier. Protected mutations copy only the readable, session-bound `evidentia_csrf` proof into `x-csrf-token`.
- The active tenant, operator, membership, and capabilities come only from `GET /api/v1/access/context`. Callers must not manufacture authority from route state, browser storage, request bodies, or cached tenant identifiers.
- Tenant selection asks the server to rotate the session. It does not assert that the operator belongs to the requested tenant.
- The API's stable error envelope is exposed as `EvidentiaApiError`, including the response correlation identifier for support and audit investigation.

## Lifecycle expectations

The access endpoints do not expose an aggregate version because the server owns session concurrency. Login creates a distinct session on every successful call, tenant selection rotates the current session, and logout revokes it. Consumers should prevent accidental duplicate submissions, but must not treat these commands as generally replay-safe.

Future business mutations that require optimistic concurrency or idempotent retry must declare version and idempotency inputs in OpenAPI. They must not implement those guarantees only in React state or SDK-private behavior. Server-side access services remain responsible for authorization checks and security audit events; the SDK supplies correlation metadata but does not create authoritative audit records.

No persistence or migration is owned by this SDK contract pass.

## Generation

Run `make generate-api-contract` after an API contract change. Commit the OpenAPI document and generated TypeScript types together. `make generated-check` fails when checked artifacts or the lockfile are stale.

## Usage

```ts
import {
  createAccessClient,
  createEvidentiaClient,
} from "@evidentia/typescript-sdk";

const transport = createEvidentiaClient({ baseUrl: "http://127.0.0.1:8000" });
const access = createAccessClient(transport);
const context = await access.getCurrentContext();
```

The application may wrap these methods with TanStack Query, but it should not issue ad hoc `fetch` requests to Evidentia endpoints.
