import createClient, {
  type Client,
  type ClientOptions,
  type Middleware,
} from "openapi-fetch";

import type { components, paths } from "./generated/evidentia.js";

const CSRF_COOKIE_NAME = "evidentia_csrf";
const CSRF_HEADER_NAME = "x-csrf-token";
const CORRELATION_HEADER_NAME = "x-correlation-id";

/** Login material accepted by the local browser-session endpoint.
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-017
 */
export type LoginRequest = components["schemas"]["LoginRequest"];

/** Display-safe tenant choice returned during authentication.
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-017
 */
export type TenantSummary = components["schemas"]["TenantSummary"];

/** Result of creating or rotating an opaque browser session.
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-017
 */
export type SessionResponse = components["schemas"]["SessionResponse"];

/** Trusted operator, tenant, membership, and capability context.
 * @skyhook-implements REQ-012
 * @skyhook-implements NFR-002
 * @skyhook-story STORY-017
 */
export type CurrentContext = components["schemas"]["CurrentContextResponse"];

/** Generated, framework-neutral transport for every public Evidentia route.
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-017
 */
export type EvidentiaClient = Client<paths>;

/** Injectable browser boundary used to read the non-secret CSRF cookie.
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-017
 */
export type CookieReader = (name: string) => string | undefined;

/** Configuration for the generated Evidentia transport.
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-017
 */
export interface EvidentiaClientOptions {
  readonly baseUrl?: string;
  readonly fetch?: ClientOptions["fetch"];
  readonly readCookie?: CookieReader;
  readonly createCorrelationId?: () => string;
}

/** Per-interaction controls that do not alter business command semantics.
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-017
 */
export interface AccessRequestOptions {
  readonly signal?: AbortSignal;
}

/** Stable SDK error carrying the public code and request correlation ID.
 * @skyhook-implements REQ-012
 * @skyhook-implements NFR-006
 * @skyhook-story STORY-017
 */
export class EvidentiaApiError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly correlationId: string | undefined;

  public constructor(
    status: number,
    code: string,
    message: string,
    correlationId?: string,
  ) {
    super(message);
    this.name = "EvidentiaApiError";
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
  }
}

/** Framework-neutral access operations used by authenticated applications.
 * @skyhook-implements REQ-012
 * @skyhook-implements NFR-002
 * @skyhook-story STORY-017
 */
export interface AccessClient {
  /** Restore non-secret session and tenant-selection state after navigation or reload. */
  getSession(options?: AccessRequestOptions): Promise<SessionResponse>;
  /** Create a new server-owned session. Repeated calls create distinct sessions. */
  login(
    request: LoginRequest,
    options?: AccessRequestOptions,
  ): Promise<SessionResponse>;
  /** Resolve tenant scope and actor authority from the server-owned session. */
  getCurrentContext(options?: AccessRequestOptions): Promise<CurrentContext>;
  /** Rotate the session into an authorized tenant; never trusts client tenant claims. */
  selectTenant(
    tenantId: string,
    options?: AccessRequestOptions,
  ): Promise<SessionResponse>;
  /** Revoke the current session. Repeated calls may resolve as already unauthenticated. */
  logout(options?: AccessRequestOptions): Promise<void>;
}

function defaultCookieReader(name: string): string | undefined {
  if (typeof document === "undefined") {
    return undefined;
  }
  const prefix = `${encodeURIComponent(name)}=`;
  const entry = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return entry === undefined
    ? undefined
    : decodeURIComponent(entry.slice(prefix.length));
}

function defaultCorrelationId(): string {
  if (typeof globalThis.crypto?.randomUUID !== "function") {
    throw new Error("A correlation ID factory is required in this runtime.");
  }
  return globalThis.crypto.randomUUID();
}

function requestMiddleware(
  readCookie: CookieReader,
  createCorrelationId: () => string,
): Middleware {
  return {
    onRequest({ request }) {
      if (!request.headers.has(CORRELATION_HEADER_NAME)) {
        request.headers.set(CORRELATION_HEADER_NAME, createCorrelationId());
      }
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
        const csrfToken = readCookie(CSRF_COOKIE_NAME);
        if (csrfToken !== undefined) {
          request.headers.set(CSRF_HEADER_NAME, csrfToken);
        }
      }
      return request;
    },
  };
}

/** Create the sole supported browser-to-API transport with credentials and request metadata.
 * @skyhook-implements REQ-012
 * @skyhook-implements NFR-006
 * @skyhook-story STORY-017
 */
export function createEvidentiaClient(
  options: EvidentiaClientOptions = {},
): EvidentiaClient {
  const clientOptions: ClientOptions = {
    baseUrl: options.baseUrl ?? "",
    credentials: "include",
  };
  if (options.fetch !== undefined) {
    clientOptions.fetch = options.fetch;
  }
  const client = createClient<paths>(clientOptions);
  client.use(
    requestMiddleware(
      options.readCookie ?? defaultCookieReader,
      options.createCorrelationId ?? defaultCorrelationId,
    ),
  );
  return client;
}

function isErrorEnvelope(
  value: unknown,
): value is components["schemas"]["ErrorResponse"] {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.code === "string" && typeof candidate.error === "string"
  );
}

function apiError(error: unknown, response: Response): EvidentiaApiError {
  const correlationId =
    response.headers.get(CORRELATION_HEADER_NAME) ?? undefined;
  if (isErrorEnvelope(error)) {
    return new EvidentiaApiError(
      response.status,
      error.code,
      error.error,
      correlationId,
    );
  }
  return new EvidentiaApiError(
    response.status,
    "invalid_error_response",
    "The service returned an invalid error response.",
    correlationId,
  );
}

/** Create access-specific commands over a generated Evidentia transport.
 * @skyhook-implements REQ-012
 * @skyhook-implements NFR-002
 * @skyhook-story STORY-017
 */
export function createAccessClient(client: EvidentiaClient): AccessClient {
  return {
    async getSession(options) {
      const signal = options?.signal;
      const result = await client.GET("/api/v1/access/session", {
        ...(signal === undefined ? {} : { signal }),
      });
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async login(request, options) {
      const signal = options?.signal;
      const result = await client.POST("/api/v1/access/sessions", {
        body: request,
        ...(signal === undefined ? {} : { signal }),
      });
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async getCurrentContext(options) {
      const signal = options?.signal;
      const result = await client.GET("/api/v1/access/context", {
        ...(signal === undefined ? {} : { signal }),
      });
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async selectTenant(tenantId, options) {
      const signal = options?.signal;
      const result = await client.PUT("/api/v1/access/session/tenant", {
        body: { tenant_id: tenantId },
        ...(signal === undefined ? {} : { signal }),
      });
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async logout(options) {
      const signal = options?.signal;
      const result = await client.DELETE("/api/v1/access/session", {
        ...(signal === undefined ? {} : { signal }),
      });
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
    },
  };
}
