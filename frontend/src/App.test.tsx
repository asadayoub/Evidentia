import {
  EvidentiaApiError,
  type AccessClient,
  type CurrentContext,
  type SessionResponse,
} from "@evidentia/typescript-sdk";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";

const ACTIVE_SESSION: SessionResponse = {
  active_tenant_id: "tenant-1",
  available_tenants: [
    {
      display_name: "Local Evidentia Workspace",
      slug: "local",
      tenant_id: "tenant-1",
    },
  ],
  operator_id: "operator-1",
  tenant_selection_required: false,
};

const TRUSTED_CONTEXT: CurrentContext = {
  authenticated_at: "2026-10-07T16:00:00Z",
  capabilities: ["access.manage", "schemas.read"],
  correlation_id: "request-1",
  display_name: "Local Administrator",
  login_identifier: "admin@localhost",
  membership_id: "membership-1",
  operator_id: "operator-1",
  session_id: "session-1",
  tenant_id: "tenant-1",
  tenant_name: "Local Evidentia Workspace",
  tenant_slug: "local",
};

function fakeAccess(overrides: Partial<AccessClient> = {}): AccessClient {
  return {
    getCurrentContext: () => Promise.resolve(TRUSTED_CONTEXT),
    getSession: () => Promise.resolve(ACTIVE_SESSION),
    login: () => Promise.resolve(ACTIVE_SESSION),
    logout: () => Promise.resolve(),
    selectTenant: () => Promise.resolve(ACTIVE_SESSION),
    ...overrides,
  };
}

describe("Evidentia authenticated application shell", () => {
  it("redirects an unauthenticated protected route to login", async () => {
    const access = fakeAccess({
      getSession: () =>
        Promise.reject(
          new EvidentiaApiError(
            401,
            "session_required",
            "Authentication is required.",
          ),
        ),
    });

    render(<App access={access} initialEntries={["/app"]} />);

    expect(
      await screen.findByRole("heading", {
        name: "Continue to your governed workspace.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Email or login identifier"),
    ).toBeInTheDocument();
  });

  it("signs in and restores trusted tenant context through the SDK", async () => {
    const login = vi.fn(() => Promise.resolve(ACTIVE_SESSION));
    const access = fakeAccess({
      getSession: () =>
        Promise.reject(
          new EvidentiaApiError(
            401,
            "session_required",
            "Authentication is required.",
          ),
        ),
      login,
    });
    render(<App access={access} initialEntries={["/login"]} />);

    fireEvent.change(
      await screen.findByLabelText("Email or login identifier"),
      {
        target: { value: "admin@localhost" },
      },
    );
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct horse battery staple" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in securely" }));

    expect(
      await screen.findByRole("heading", { name: "Overview" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Local Evidentia Workspace")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Schemas" })).toHaveLength(2);
    expect(login).toHaveBeenCalledWith({
      login_identifier: "admin@localhost",
      password: "correct horse battery staple",
    });
  });

  it("requires an authorized tenant selection when the session is tenantless", async () => {
    const tenantless: SessionResponse = {
      ...ACTIVE_SESSION,
      active_tenant_id: null,
      tenant_selection_required: true,
    };
    const selectTenant = vi.fn(() => Promise.resolve(ACTIVE_SESSION));
    const access = fakeAccess({
      getSession: () => Promise.resolve(tenantless),
      selectTenant,
    });
    render(<App access={access} initialEntries={["/app"]} />);

    fireEvent.change(await screen.findByLabelText("Workspace"), {
      target: { value: "tenant-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Open workspace" }));

    expect(
      await screen.findByRole("heading", { name: "Overview" }),
    ).toBeInTheDocument();
    expect(selectTenant).toHaveBeenCalledWith("tenant-1");
  });

  it("hides navigation that the trusted context does not authorize", async () => {
    const access = fakeAccess({
      getCurrentContext: () =>
        Promise.resolve({
          ...TRUSTED_CONTEXT,
          capabilities: ["access.manage"],
        }),
    });

    render(<App access={access} initialEntries={["/app"]} />);

    expect(
      await screen.findByRole("heading", { name: "Overview" }),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole("link", { name: "Schemas" })).toHaveLength(0);
  });

  it("shows a safe forbidden state without rendering the workspace", async () => {
    const access = fakeAccess({
      getCurrentContext: () =>
        Promise.reject(
          new EvidentiaApiError(
            403,
            "access_denied",
            "The request is not authorized.",
          ),
        ),
    });

    render(<App access={access} initialEntries={["/app"]} />);

    expect(
      await screen.findByRole("heading", { name: "Access unavailable" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Overview" }),
    ).not.toBeInTheDocument();
  });
});
