import {
  EvidentiaApiError,
  type AccessClient,
  type CurrentContext,
  type SessionResponse,
} from "@evidentia/typescript-sdk";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
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
  it("has no detectable accessibility violations in the authenticated shell", async () => {
    const { container } = render(
      <App access={fakeAccess()} initialEntries={["/app"]} />,
    );

    expect(
      await screen.findByRole("heading", { name: "Overview" }),
    ).toBeInTheDocument();
    const result = await axe.run(container, {
      rules: {
        // jsdom has no layout engine; contrast is verified in a real browser.
        "color-contrast": { enabled: false },
      },
    });

    expect(result.violations).toEqual([]);
  });

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

  it("returns to the originally requested capability after sign in", async () => {
    const getSession = vi
      .fn<AccessClient["getSession"]>()
      .mockRejectedValue(
        new EvidentiaApiError(
          401,
          "session_required",
          "Authentication is required.",
        ),
      );
    const access = fakeAccess({ getSession });

    render(<App access={access} initialEntries={["/app/schemas"]} />);

    fireEvent.change(
      await screen.findByLabelText("Email or login identifier"),
      { target: { value: "admin@localhost" } },
    );
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct horse battery staple" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in securely" }));

    expect(
      await screen.findByRole("heading", { name: "Schemas" }),
    ).toBeInTheDocument();
  });

  it("shows a stable authentication error without exposing supplied credentials", async () => {
    const access = fakeAccess({
      getSession: () =>
        Promise.reject(
          new EvidentiaApiError(
            401,
            "session_required",
            "Authentication is required.",
          ),
        ),
      login: () =>
        Promise.reject(
          new EvidentiaApiError(
            401,
            "credentials_invalid",
            "The supplied credentials are not valid.",
          ),
        ),
    });

    render(<App access={access} initialEntries={["/login"]} />);

    fireEvent.change(
      await screen.findByLabelText("Email or login identifier"),
      { target: { value: "unknown@example.test" } },
    );
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "never-render-this-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in securely" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The supplied credentials are not valid.",
    );
    expect(screen.queryByText("never-render-this-password")).toBeNull();
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

  it("explains when a tenantless operator has no active memberships", async () => {
    const access = fakeAccess({
      getSession: () =>
        Promise.resolve({
          ...ACTIVE_SESSION,
          active_tenant_id: null,
          available_tenants: [],
          tenant_selection_required: true,
        }),
    });

    render(<App access={access} initialEntries={["/app"]} />);

    expect(
      await screen.findByRole("heading", { name: "No active workspaces" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open workspace" })).toBeNull();
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

  it("recovers deterministically after a transient session restore failure", async () => {
    const getSession = vi
      .fn<AccessClient["getSession"]>()
      .mockRejectedValueOnce(new TypeError("network unavailable"))
      .mockResolvedValue(ACTIVE_SESSION);
    const access = fakeAccess({ getSession });

    render(<App access={access} initialEntries={["/app"]} />);

    expect(
      await screen.findByRole("heading", { name: "Evidentia is unavailable" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(
      await screen.findByRole("heading", { name: "Overview" }),
    ).toBeInTheDocument();
    expect(getSession).toHaveBeenCalledTimes(2);
  });

  it("returns an expired context to sign in without showing protected content", async () => {
    const getSession = vi
      .fn<AccessClient["getSession"]>()
      .mockResolvedValueOnce(ACTIVE_SESSION)
      .mockRejectedValue(
        new EvidentiaApiError(
          401,
          "session_invalid",
          "The session is no longer valid.",
        ),
      );
    const access = fakeAccess({
      getCurrentContext: () =>
        Promise.reject(
          new EvidentiaApiError(
            401,
            "session_invalid",
            "The session is no longer valid.",
          ),
        ),
      getSession,
    });

    render(<App access={access} initialEntries={["/app/schemas"]} />);

    expect(
      await screen.findByRole("heading", {
        name: "Continue to your governed workspace.",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Schemas" })).toBeNull();
  });

  it("clears the local authority view after confirmed logout", async () => {
    const logout = vi.fn(() => Promise.resolve());
    const getSession = vi
      .fn<AccessClient["getSession"]>()
      .mockResolvedValueOnce(ACTIVE_SESSION)
      .mockRejectedValue(
        new EvidentiaApiError(
          401,
          "session_invalid",
          "The session is no longer valid.",
        ),
      );
    const access = fakeAccess({ getSession, logout });

    render(<App access={access} initialEntries={["/app"]} />);

    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(logout).toHaveBeenCalledOnce());
    expect(
      await screen.findByRole("heading", {
        name: "Continue to your governed workspace.",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Overview" })).toBeNull();
  });
});
