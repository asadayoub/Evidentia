import {
  EvidentiaApiError,
  type AccessClient,
  type CurrentContext,
  type SessionResponse,
} from "@evidentia/typescript-sdk";
import {
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import {
  Navigate,
  useLocation,
  useNavigate,
  type Location,
} from "react-router";

const SESSION_QUERY_KEY = ["access", "session"] as const;
const CONTEXT_QUERY_KEY = ["access", "context"] as const;

interface IntendedLocationState {
  readonly from?: unknown;
}

function intendedPath(location: Location): string {
  const state = location.state as IntendedLocationState | null;
  return typeof state?.from === "string" && state.from.startsWith("/app")
    ? state.from
    : "/app";
}

function isApiStatus(error: unknown, status: number): boolean {
  return error instanceof EvidentiaApiError && error.status === status;
}

function publicError(error: unknown): string {
  if (error instanceof EvidentiaApiError) {
    return error.message;
  }
  return "Evidentia could not reach the service. Check that the API is running and try again.";
}

/** Query contract for restoring the non-secret browser session.
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-017
 */
export function sessionQueryOptions(access: AccessClient) {
  return queryOptions({
    queryKey: SESSION_QUERY_KEY,
    queryFn: ({ signal }) => access.getSession({ signal }),
    retry: false,
    staleTime: 30_000,
  });
}

/** Query contract for the server-authoritative operator and tenant context.
 * @skyhook-implements NFR-002
 * @skyhook-implements CON-005
 * @skyhook-story STORY-017
 */
export function contextQueryOptions(access: AccessClient) {
  return queryOptions({
    queryKey: CONTEXT_QUERY_KEY,
    queryFn: ({ signal }) => access.getCurrentContext({ signal }),
    retry: false,
    staleTime: 30_000,
  });
}

/** Accessible progress or failure surface for asynchronous access operations.
 * @skyhook-implements NFR-005
 * @skyhook-story STORY-017
 */
export function AccessStatus({
  title,
  message,
  action,
}: {
  readonly title: string;
  readonly message: string;
  readonly action?: () => void;
}) {
  return (
    <main className="centered-page">
      <section aria-labelledby="access-status-title" className="status-card">
        <p className="eyebrow">Evidentia access</p>
        <h1 id="access-status-title">{title}</h1>
        <p>{message}</p>
        {action === undefined ? null : (
          <button
            className="button button-primary"
            onClick={action}
            type="button"
          >
            Try again
          </button>
        )}
      </section>
    </main>
  );
}

/** Login experience backed only by the generated SDK access contract.
 * @skyhook-implements REQ-012
 * @skyhook-implements NFR-005
 * @skyhook-story STORY-017
 */
export function LoginPage({ access }: { readonly access: AccessClient }) {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const session = useQuery(sessionQueryOptions(access));
  const [loginIdentifier, setLoginIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () =>
      access.login({ login_identifier: loginIdentifier, password }),
    onSuccess: (restored) => {
      queryClient.setQueryData(SESSION_QUERY_KEY, restored);
      void navigate(
        restored.tenant_selection_required
          ? "/select-tenant"
          : intendedPath(location),
        { replace: true, state: { from: intendedPath(location) } },
      );
    },
  });

  useEffect(() => {
    if (session.data !== undefined) {
      void navigate(
        session.data.tenant_selection_required
          ? "/select-tenant"
          : intendedPath(location),
        { replace: true, state: { from: intendedPath(location) } },
      );
    }
  }, [location, navigate, session.data]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    login.mutate();
  }

  if (session.isPending) {
    return (
      <AccessStatus
        message="Checking for an existing secure session."
        title="Restoring your session"
      />
    );
  }

  return (
    <main className="login-page">
      <section aria-labelledby="login-title" className="login-intro">
        <a className="brand" href="/" aria-label="Evidentia home">
          <span className="brand-mark" aria-hidden="true">
            E
          </span>
          <span>Evidentia</span>
        </a>
        <div>
          <p className="eyebrow">Evidence-led operations</p>
          <h1 id="login-title">Continue to your governed workspace.</h1>
          <p className="lead">
            Review documents, manage evolving schemas, and preserve every
            material decision in one attributable workflow.
          </p>
        </div>
        <p className="security-note">
          Your session is stored in a secure server-managed cookie, never in
          browser storage.
        </p>
      </section>

      <section aria-labelledby="sign-in-title" className="login-card">
        <div>
          <p className="eyebrow">Authorized access</p>
          <h2 id="sign-in-title">Sign in</h2>
          <p>
            Use the local operator credentials configured for this installation.
          </p>
        </div>
        <form className="form-stack" onSubmit={submit}>
          <label htmlFor="login-identifier">Email or login identifier</label>
          <input
            autoComplete="username"
            id="login-identifier"
            name="login_identifier"
            onChange={(event) => setLoginIdentifier(event.target.value)}
            required
            type="text"
            value={loginIdentifier}
          />
          <label htmlFor="login-password">Password</label>
          <input
            autoComplete="current-password"
            id="login-password"
            name="password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
          {login.error === null ? null : (
            <p className="error-banner" role="alert">
              {publicError(login.error)}
            </p>
          )}
          <button
            className="button button-primary"
            disabled={login.isPending}
            type="submit"
          >
            {login.isPending ? "Signing in…" : "Sign in securely"}
          </button>
        </form>
      </section>
    </main>
  );
}

/** Tenant choice shown only when a restored session has multiple valid memberships.
 * @skyhook-implements NFR-002
 * @skyhook-implements CON-005
 * @skyhook-story STORY-017
 */
export function TenantSelectionPage({
  access,
}: {
  readonly access: AccessClient;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const session = useQuery(sessionQueryOptions(access));
  const [tenantId, setTenantId] = useState("");
  const selection = useMutation({
    mutationFn: () => access.selectTenant(tenantId),
    onSuccess: (restored) => {
      queryClient.setQueryData(SESSION_QUERY_KEY, restored);
      void queryClient.invalidateQueries({ queryKey: CONTEXT_QUERY_KEY });
      void navigate(intendedPath(location), { replace: true });
    },
  });

  if (session.isPending) {
    return (
      <AccessStatus
        message="Loading the workspaces available to your account."
        title="Loading workspaces"
      />
    );
  }
  if (session.error !== null) {
    if (isApiStatus(session.error, 401)) {
      return (
        <Navigate
          replace
          state={{ from: intendedPath(location) }}
          to="/login"
        />
      );
    }
    return (
      <AccessStatus
        action={() => void session.refetch()}
        message={publicError(session.error)}
        title="Workspaces are unavailable"
      />
    );
  }
  if (!session.data.tenant_selection_required) {
    return <Navigate replace to={intendedPath(location)} />;
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    selection.mutate();
  }

  return (
    <main className="centered-page">
      <section aria-labelledby="tenant-title" className="selection-card">
        <p className="eyebrow">Workspace boundary</p>
        <h1 id="tenant-title">Choose where you are working</h1>
        <p>
          Your selection establishes the tenant boundary for data and
          permissions in this session.
        </p>
        {session.data.available_tenants.length === 0 ? (
          <div className="empty-state" role="status">
            <h2>No active workspaces</h2>
            <p>
              Ask an administrator to activate a tenant membership for your
              account.
            </p>
          </div>
        ) : (
          <form className="form-stack" onSubmit={submit}>
            <label htmlFor="tenant-choice">Workspace</label>
            <select
              id="tenant-choice"
              onChange={(event) => setTenantId(event.target.value)}
              required
              value={tenantId}
            >
              <option value="">Select a workspace</option>
              {session.data.available_tenants.map((tenant) => (
                <option key={tenant.tenant_id} value={tenant.tenant_id}>
                  {tenant.display_name}
                </option>
              ))}
            </select>
            {selection.error === null ? null : (
              <p className="error-banner" role="alert">
                {publicError(selection.error)}
              </p>
            )}
            <button
              className="button button-primary"
              disabled={selection.isPending}
              type="submit"
            >
              {selection.isPending ? "Opening workspace…" : "Open workspace"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}

/** Redirect unauthenticated or tenantless sessions before protected content renders.
 * @skyhook-implements NFR-002
 * @skyhook-story STORY-017
 */
export function ProtectedRoute({
  access,
  children,
}: {
  readonly access: AccessClient;
  readonly children: React.ReactNode;
}) {
  const location = useLocation();
  const session = useQuery(sessionQueryOptions(access));

  if (session.isPending) {
    return (
      <AccessStatus
        message="Confirming your secure session and workspace boundary."
        title="Opening Evidentia"
      />
    );
  }
  if (session.error !== null) {
    if (isApiStatus(session.error, 401)) {
      return (
        <Navigate
          replace
          state={{ from: `${location.pathname}${location.search}` }}
          to="/login"
        />
      );
    }
    return (
      <AccessStatus
        action={() => void session.refetch()}
        message={publicError(session.error)}
        title="Evidentia is unavailable"
      />
    );
  }
  if (session.data.tenant_selection_required) {
    return (
      <Navigate
        replace
        state={{ from: `${location.pathname}${location.search}` }}
        to="/select-tenant"
      />
    );
  }
  return children;
}

/** Load trusted context for the authenticated application shell.
 * @skyhook-implements NFR-002
 * @skyhook-story STORY-017
 */
export function useTrustedContext(access: AccessClient) {
  return useQuery(contextQueryOptions(access));
}

/** Remove cached authority after the server confirms logout.
 * @skyhook-implements NFR-002
 * @skyhook-story STORY-017
 */
export function useLogout(access: AccessClient) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => access.logout(),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ["access"] });
      void navigate("/login", { replace: true });
    },
  });
}

/** Determine whether trusted context grants a navigation capability.
 * @skyhook-implements NFR-002
 * @skyhook-story STORY-017
 */
export function hasCapability(
  context: CurrentContext,
  capability: string,
): boolean {
  return context.capabilities.includes(capability);
}

/** Replace cached session state after an authorized access mutation.
 * @skyhook-story STORY-017
 */
export type SessionCacheValue = SessionResponse;
