import { describe, expect, it, vi } from "vitest";

import {
  accessOperationIds,
  createAccessClient,
  createDocumentClient,
  createEvidentiaClient,
  createSchemaClient,
  EvidentiaApiError,
  schemaOperationIds,
  documentOperationIds,
  sdkVersion,
} from "../src/index";

describe("TypeScript SDK boundary", () => {
  it("exposes its supported version", () => {
    expect(sdkVersion()).toBe("0.1.0");
  });

  it("exposes access operations generated from the checked contract", () => {
    expect(accessOperationIds).toEqual([
      "access_get_current_context",
      "access_get_session",
      "access_login_local",
      "access_logout",
      "access_select_tenant",
    ]);
  });

  it("exposes schema operations generated from the checked contract", () => {
    expect(schemaOperationIds).toEqual([
      "schemas_apply_import",
      "schemas_create_draft",
      "schemas_export_draft_package",
      "schemas_export_publication_package",
      "schemas_get_draft",
      "schemas_get_publication",
      "schemas_list_drafts",
      "schemas_preview_import",
      "schemas_publish_draft",
      "schemas_replace_draft",
    ]);
  });

  it("exposes document operations generated from the checked contract", () => {
    expect(documentOperationIds).toEqual([
      "documents_get_custody",
      "documents_upload_original",
    ]);
  });

  it("sends credentials, CSRF proof, and a caller-visible correlation ID", async () => {
    const fetch = vi.fn(async (request: Request) => {
      expect(request.credentials).toBe("include");
      expect(request.headers.get("x-csrf-token")).toBe("csrf-proof");
      expect(request.headers.get("x-correlation-id")).toBe("request-123");
      expect(await request.json()).toEqual({ tenant_id: "tenant-2" });
      return Response.json({
        active_tenant_id: "tenant-2",
        available_tenants: [
          {
            display_name: "Tenant Two",
            slug: "tenant-two",
            tenant_id: "tenant-2",
          },
        ],
        operator_id: "operator-1",
        tenant_selection_required: false,
      });
    });
    const client = createAccessClient(
      createEvidentiaClient({
        baseUrl: "https://api.example.test",
        createCorrelationId: () => "request-123",
        fetch,
        readCookie: (name) =>
          name === "evidentia_csrf" ? "csrf-proof" : undefined,
      }),
    );

    const session = await client.selectTenant("tenant-2");

    expect(session.active_tenant_id).toBe("tenant-2");
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("returns the generated trusted-context shape", async () => {
    const controller = new AbortController();
    controller.abort();
    const fetch = vi.fn((request: Request) => {
      expect(request.signal.aborted).toBe(true);
      return Promise.resolve(
        Response.json({
          authenticated_at: "2026-10-07T16:00:00Z",
          capabilities: ["schema:read"],
          correlation_id: "request-456",
          display_name: "Ada Operator",
          login_identifier: "ada@example.test",
          membership_id: "membership-1",
          operator_id: "operator-1",
          session_id: "session-1",
          tenant_id: "tenant-1",
          tenant_name: "Tenant One",
          tenant_slug: "tenant-one",
        }),
      );
    });
    const client = createAccessClient(
      createEvidentiaClient({
        baseUrl: "https://api.example.test",
        createCorrelationId: () => "request-456",
        fetch,
      }),
    );

    const context = await client.getCurrentContext({
      signal: controller.signal,
    });

    expect(context.tenant_id).toBe("tenant-1");
    expect(context.capabilities).toEqual(["schema:read"]);
  });

  it("maps stable API failures without trusting malformed payloads", async () => {
    const client = createAccessClient(
      createEvidentiaClient({
        baseUrl: "https://api.example.test",
        createCorrelationId: () => "request-789",
        fetch: () =>
          Promise.resolve(
            Response.json(
              {
                code: "session_invalid",
                error: "The session is invalid or expired.",
              },
              {
                headers: { "x-correlation-id": "response-789" },
                status: 401,
              },
            ),
          ),
      }),
    );

    await expect(client.getCurrentContext()).rejects.toEqual(
      expect.objectContaining<Partial<EvidentiaApiError>>({
        code: "session_invalid",
        correlationId: "response-789",
        status: 401,
      }),
    );
  });

  it("sends schema idempotency and browser security metadata", async () => {
    const fetch = vi.fn(async (request: Request) => {
      expect(request.headers.get("idempotency-key")).toBe("draft-command-1");
      expect(request.headers.get("x-csrf-token")).toBe("csrf-proof");
      expect(await request.json()).toEqual({
        content: { artifacts: [], fields: [], modules: [] },
      });
      return Response.json(
        {
          content: { artifacts: [], fields: [], modules: [] },
          created_at: "2026-10-07T16:00:00Z",
          created_by: "operator-1",
          revision: 1,
          schema_id: "00000000-0000-4000-8000-000000000001",
          updated_at: "2026-10-07T16:00:00Z",
          updated_by: "operator-1",
          version: 1,
        },
        { status: 201 },
      );
    });
    const client = createSchemaClient(
      createEvidentiaClient({
        baseUrl: "https://api.example.test",
        createCorrelationId: () => "request-schema-1",
        fetch,
        readCookie: () => "csrf-proof",
      }),
    );

    const draft = await client.createDraft(
      { artifacts: [], fields: [], modules: [] },
      { idempotencyKey: "draft-command-1" },
    );

    expect(draft.revision).toBe(1);
  });

  it("uploads multipart bytes with idempotency, CSRF, and correlation metadata", async () => {
    const fetch = vi.fn(async (request: Request) => {
      expect(request.headers.get("idempotency-key")).toBe("original-upload-1");
      expect(request.headers.get("x-csrf-token")).toBe("csrf-proof");
      expect(request.headers.get("x-correlation-id")).toBe("document-request-1");
      expect(request.headers.get("content-type")).toContain("multipart/form-data");
      const form = await request.formData();
      expect(form.get("document")).toBeInstanceOf(File);
      expect((form.get("document") as File).name).toBe("invoice.pdf");
      return Response.json({
        byte_size: 12,
        content_sha256: "a".repeat(64),
        created_at: "2026-10-08T08:00:00Z",
        document_id: "document-1",
        failure_code: null,
        media_type: "application/pdf",
        original_filename: "invoice.pdf",
        revision: 2,
        status: "preserved",
        updated_at: "2026-10-08T08:00:00Z",
      }, { status: 201 });
    });
    const client = createDocumentClient(
      createEvidentiaClient({
        baseUrl: "https://api.example.test",
        createCorrelationId: () => "document-request-1",
        fetch,
        readCookie: () => "csrf-proof",
      }),
    );

    const receipt = await client.uploadOriginal(
      new File(["%PDF fixture"], "invoice.pdf", { type: "application/pdf" }),
      "original-upload-1",
    );

    expect(receipt.status).toBe("preserved");
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("previews and applies portable packages through generated operations", async () => {
    const requests: Request[] = [];
    const fetch = vi.fn(async (request: Request) => {
      requests.push(request);
      const body: unknown = await request.json();
      if (request.url.endsWith("/imports/preview")) {
        return Response.json({
          canonical_sha256: "a".repeat(64),
          compatibility: null,
          content: { artifacts: [], fields: [], modules: [] },
          creates_new_draft: true,
          envelope_version: 1,
          format: "evidentia.schema-draft",
          kind: "draft",
          source_schema_id: "00000000-0000-4000-8000-000000000001",
          source_schema_version: 1,
          target_revision: null,
          target_schema_id: null,
        });
      }
      expect(request.headers.get("idempotency-key")).toBe("import-1");
      expect(body).toEqual({
        package: { format: "evidentia.schema-draft", version: 1 },
      });
      return Response.json({
        created: true,
        draft: {
          content: { artifacts: [], fields: [], modules: [] },
          created_at: "2026-10-08T06:00:00Z",
          created_by: "operator-1",
          revision: 1,
          schema_id: "00000000-0000-4000-8000-000000000002",
          updated_at: "2026-10-08T06:00:00Z",
          updated_by: "operator-1",
          version: 1,
        },
        package_sha256: "a".repeat(64),
      });
    });
    const client = createSchemaClient(
      createEvidentiaClient({
        baseUrl: "https://api.example.test",
        createCorrelationId: () => "request-import-1",
        fetch,
        readCookie: () => "csrf-proof",
      }),
    );
    const schemaPackage = {
      format: "evidentia.schema-draft",
      version: 1,
    };

    const preview = await client.previewImport(schemaPackage);
    const applied = await client.applyImport(schemaPackage, undefined, {
      idempotencyKey: "import-1",
    });

    expect(preview.creates_new_draft).toBe(true);
    expect(applied.created).toBe(true);
    expect(requests).toHaveLength(2);
  });
});
