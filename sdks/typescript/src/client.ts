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

/** Dynamic, domain-validated content for a mutable schema draft.
 * @skyhook-implements REQ-003
 * @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
 */
export type SchemaDraftContent =
  components["schemas"]["SchemaDraftContentRequest"];

/** Mutable draft plus optimistic-concurrency and audit metadata.
 * @skyhook-implements REQ-003
 * @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
 */
export type SchemaDraft = components["schemas"]["SchemaDraftResponse"];

/** Cursor page of tenant-visible schema drafts.
 * @skyhook-implements REQ-003
 * @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
 */
export type SchemaDraftPage = components["schemas"]["SchemaDraftPageResponse"];

/** Immutable publication snapshot and provenance.
 * @skyhook-implements REQ-003
 * @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
 */
export type SchemaPublication =
  components["schemas"]["SchemaPublicationResponse"];

/** Atomic publication result including the advanced next draft.
 * @skyhook-implements REQ-003
 * @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
 */
export type PublishSchemaResult =
  components["schemas"]["PublishSchemaDraftResponse"];

/** Validated preview of portable schema content and its target impact.
 * @skyhook-implements REQ-003
 * @skyhook-story STORY-018
 */
export type SchemaImportPreview =
  components["schemas"]["SchemaImportPreviewResponse"];

/** Result of applying a package to a new or existing working draft.
 * @skyhook-implements REQ-003
 * @skyhook-implements NFR-001
 * @skyhook-story STORY-018
 */
export type ApplySchemaImportResult =
  components["schemas"]["ApplySchemaImportResponse"];

/** JSON object carried by the versioned portable schema envelope.
 * @skyhook-implements REQ-003
 * @skyhook-story STORY-018
 */
export type SchemaPackage = Record<string, unknown>;

/** Optional existing-draft target for preview and apply operations.
 * @skyhook-implements NFR-001
 * @skyhook-story STORY-018
 */
export interface SchemaImportTarget {
  readonly schemaId: string;
  readonly expectedRevision: number;
}

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

/** Optional controls for schema read operations.
 * @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
 */
export type SchemaRequestOptions = AccessRequestOptions;

/** Required replay identity and optional cancellation for schema mutations.
 * @skyhook-implements NFR-001
 * @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
 */
export interface SchemaMutationOptions extends SchemaRequestOptions {
  readonly idempotencyKey: string;
}

/** Pagination controls for deterministic schema draft traversal.
 * @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
 */
export interface SchemaDraftListOptions extends SchemaRequestOptions {
  readonly cursor?: string;
  readonly limit?: number;
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

/** Governed schema lifecycle operations for authenticated applications.
 * @skyhook-implements REQ-003
 * @skyhook-implements NFR-001
 * @skyhook-implements NFR-002
 * @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
 */
export interface SchemaClient {
  createDraft(
    content: SchemaDraftContent,
    options: SchemaMutationOptions,
  ): Promise<SchemaDraft>;
  listDrafts(options?: SchemaDraftListOptions): Promise<SchemaDraftPage>;
  getDraft(
    schemaId: string,
    options?: SchemaRequestOptions,
  ): Promise<SchemaDraft>;
  replaceDraft(
    schemaId: string,
    content: SchemaDraftContent,
    expectedRevision: number,
    options: SchemaMutationOptions,
  ): Promise<SchemaDraft>;
  publishDraft(
    schemaId: string,
    expectedRevision: number,
    options: SchemaMutationOptions & { readonly acknowledgement?: string },
  ): Promise<PublishSchemaResult>;
  getPublication(
    schemaId: string,
    version: number,
    options?: SchemaRequestOptions,
  ): Promise<SchemaPublication>;
  exportDraftPackage(
    schemaId: string,
    options?: SchemaRequestOptions,
  ): Promise<SchemaPackage>;
  exportPublicationPackage(
    schemaId: string,
    version: number,
    options?: SchemaRequestOptions,
  ): Promise<SchemaPackage>;
  previewImport(
    schemaPackage: SchemaPackage,
    target?: Pick<SchemaImportTarget, "schemaId">,
    options?: SchemaRequestOptions,
  ): Promise<SchemaImportPreview>;
  applyImport(
    schemaPackage: SchemaPackage,
    target: SchemaImportTarget | undefined,
    options: SchemaMutationOptions,
  ): Promise<ApplySchemaImportResult>;
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

/** Create schema-specific commands over the generated Evidentia transport.
 * @skyhook-implements REQ-003
 * @skyhook-implements NFR-001
 * @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
 * @skyhook-story 265YM4FNANJAH2J338BKAWFXDM
 */
export function createSchemaClient(client: EvidentiaClient): SchemaClient {
  return {
    async createDraft(content, options) {
      const result = await client.POST("/api/v1/schemas/drafts", {
        body: { content },
        params: { header: { "Idempotency-Key": options.idempotencyKey } },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      });
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async listDrafts(options) {
      const result = await client.GET("/api/v1/schemas/drafts", {
        params: {
          query: {
            ...(options?.cursor === undefined
              ? {}
              : { cursor: options.cursor }),
            ...(options?.limit === undefined ? {} : { limit: options.limit }),
          },
        },
        ...(options?.signal === undefined ? {} : { signal: options.signal }),
      });
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async getDraft(schemaId, options) {
      const result = await client.GET("/api/v1/schemas/drafts/{schema_id}", {
        params: { path: { schema_id: schemaId } },
        ...(options?.signal === undefined ? {} : { signal: options.signal }),
      });
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async replaceDraft(schemaId, content, expectedRevision, options) {
      const result = await client.PUT("/api/v1/schemas/drafts/{schema_id}", {
        params: {
          header: { "Idempotency-Key": options.idempotencyKey },
          path: { schema_id: schemaId },
        },
        body: { content, expected_revision: expectedRevision },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      });
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async publishDraft(schemaId, expectedRevision, options) {
      const result = await client.POST(
        "/api/v1/schemas/drafts/{schema_id}/publications",
        {
          params: {
            header: { "Idempotency-Key": options.idempotencyKey },
            path: { schema_id: schemaId },
          },
          body: {
            expected_revision: expectedRevision,
            ...(options.acknowledgement === undefined
              ? {}
              : { acknowledgement: options.acknowledgement }),
          },
          ...(options.signal === undefined ? {} : { signal: options.signal }),
        },
      );
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async getPublication(schemaId, version, options) {
      const result = await client.GET(
        "/api/v1/schemas/{schema_id}/versions/{version}",
        {
          params: { path: { schema_id: schemaId, version } },
          ...(options?.signal === undefined ? {} : { signal: options.signal }),
        },
      );
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async exportDraftPackage(schemaId, options) {
      const result = await client.GET(
        "/api/v1/schemas/drafts/{schema_id}/package",
        {
          params: { path: { schema_id: schemaId } },
          ...(options?.signal === undefined ? {} : { signal: options.signal }),
        },
      );
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async exportPublicationPackage(schemaId, version, options) {
      const result = await client.GET(
        "/api/v1/schemas/{schema_id}/versions/{version}/package",
        {
          params: { path: { schema_id: schemaId, version } },
          ...(options?.signal === undefined ? {} : { signal: options.signal }),
        },
      );
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async previewImport(schemaPackage, target, options) {
      const result = await client.POST("/api/v1/schemas/imports/preview", {
        body: {
          package: schemaPackage,
          ...(target === undefined
            ? {}
            : { target_schema_id: target.schemaId }),
        },
        ...(options?.signal === undefined ? {} : { signal: options.signal }),
      });
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },

    async applyImport(schemaPackage, target, options) {
      const result = await client.POST("/api/v1/schemas/imports", {
        params: { header: { "Idempotency-Key": options.idempotencyKey } },
        body: {
          package: schemaPackage,
          ...(target === undefined
            ? {}
            : {
                target_schema_id: target.schemaId,
                expected_revision: target.expectedRevision,
              }),
        },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      });
      if (result.error !== undefined) {
        throw apiError(result.error, result.response);
      }
      return result.data;
    },
  };
}
