import { describe, expect, it, vi } from "vitest";

import {
  accessOperationIds,
  createAccessClient,
  createEvidentiaClient,
  EvidentiaApiError,
  sdkVersion,
} from "../src/index";

describe("TypeScript SDK boundary", () => {
  it("exposes its supported version", () => {
    expect(sdkVersion()).toBe("0.1.0");
  });

  it("exposes access operations generated from the checked contract", () => {
    expect(accessOperationIds).toEqual([
      "access_get_current_context",
      "access_login_local",
      "access_logout",
      "access_select_tenant",
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
});
