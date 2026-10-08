import {
  EvidentiaApiError,
  type AccessClient,
  type CurrentContext,
  type DocumentClient,
  type SchemaClient,
} from "@evidentia/typescript-sdk";
import {
  QueryClient,
  QueryClientProvider,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Link,
  MemoryRouter,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router";

import {
  browserAccessClient,
  browserDocumentClient,
  browserSchemaClient,
} from "./api";
import {
  AccessStatus,
  hasCapability,
  LoginPage,
  ProtectedRoute,
  TenantSelectionPage,
  useLogout,
  useTrustedContext,
} from "./auth";
import {
  SchemaDraftEditorPage,
  SchemaWorkbenchPage,
} from "./schemas/workbench";
import { DocumentIntakePage } from "./documents/intake";

interface NavigationItem {
  readonly label: string;
  readonly to: string;
  readonly capability?: string;
  readonly end?: boolean;
}

const NAVIGATION: readonly NavigationItem[] = [
  { label: "Overview", to: "/app", end: true },
  { label: "Schemas", to: "/app/schemas", capability: "schemas.read" },
  { label: "Documents", to: "/app/documents", capability: "documents.read" },
];

/** Injectable application boundary used by tests and alternative hosts.
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-017
 */
export interface AppProps {
  readonly access?: AccessClient;
  readonly schemas?: SchemaClient;
  readonly documents?: DocumentClient;
  readonly initialEntries?: readonly string[];
}

function Navigation({ context }: { readonly context: CurrentContext }) {
  return (
    <ul className="navigation-list">
      {NAVIGATION.filter(
        (item) =>
          item.capability === undefined ||
          hasCapability(context, item.capability),
      ).map((item) => (
        <li key={item.to}>
          <NavLink
            className={({ isActive }) =>
              isActive
                ? "navigation-link navigation-link-active"
                : "navigation-link"
            }
            to={item.to}
            {...(item.end === undefined ? {} : { end: item.end })}
          >
            {item.label}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

function SessionInvalidRedirect() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const location = useLocation();

  useEffect(() => {
    queryClient.removeQueries({ queryKey: ["access"] });
    void navigate("/login", {
      replace: true,
      state: { from: `${location.pathname}${location.search}` },
    });
  }, [location.pathname, location.search, navigate, queryClient]);

  return (
    <AccessStatus
      message="Your session has ended. Returning you to secure sign in."
      title="Session expired"
    />
  );
}

function ApplicationShell({ access }: { readonly access: AccessClient }) {
  const context = useTrustedContext(access);
  const logout = useLogout(access);

  if (context.isPending) {
    return (
      <AccessStatus
        message="Loading your trusted operator and workspace context."
        title="Preparing your workspace"
      />
    );
  }
  if (context.error !== null) {
    if (
      context.error instanceof EvidentiaApiError &&
      context.error.status === 401
    ) {
      return <SessionInvalidRedirect />;
    }
    if (
      context.error instanceof EvidentiaApiError &&
      context.error.status === 403
    ) {
      return (
        <AccessStatus
          message="Your account does not have permission to open this workspace. Ask an administrator to review your membership."
          title="Access unavailable"
        />
      );
    }
    return (
      <AccessStatus
        action={() => void context.refetch()}
        message={
          context.error instanceof EvidentiaApiError
            ? context.error.message
            : "The trusted workspace context could not be loaded."
        }
        title="Workspace unavailable"
      />
    );
  }

  return (
    <div className="application-frame">
      <header className="topbar">
        <Link className="brand brand-compact" to="/app">
          <span className="brand-mark" aria-hidden="true">
            E
          </span>
          <span>Evidentia</span>
        </Link>
        <div className="topbar-context">
          <div className="context-copy">
            <span className="context-tenant">{context.data.tenant_name}</span>
            <span className="context-operator">
              {context.data.display_name}
            </span>
          </div>
          <button
            className="button button-quiet"
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
            type="button"
          >
            {logout.isPending ? "Signing out…" : "Sign out"}
          </button>
        </div>
      </header>

      <aside className="sidebar">
        <nav aria-label="Primary navigation">
          <p className="navigation-label">Workspace</p>
          <Navigation context={context.data} />
        </nav>
        <div className="sidebar-footnote">
          <span className="status-dot" aria-hidden="true" />
          Secure tenant context
        </div>
      </aside>

      <details className="mobile-navigation">
        <summary>Workspace navigation</summary>
        <nav aria-label="Mobile primary navigation">
          <Navigation context={context.data} />
        </nav>
      </details>

      <main className="application-content" id="main-content">
        {logout.error === null ? null : (
          <p className="error-banner" role="alert">
            Sign out could not be completed. Your session remains active; please
            try again.
          </p>
        )}
        <Outlet context={context.data} />
      </main>
    </div>
  );
}

function Dashboard() {
  return (
    <div className="content-stack">
      <header className="page-header">
        <p className="eyebrow">Operational workspace</p>
        <h1>Overview</h1>
        <p>
          Your authenticated Evidentia shell is ready. Product capabilities will
          appear here as their governed workflows become available.
        </p>
      </header>
      <section aria-labelledby="foundation-title" className="feature-panel">
        <div>
          <p className="panel-kicker">Foundation online</p>
          <h2 id="foundation-title">Trusted access is active</h2>
        </div>
        <p>
          The browser restored a server-owned session and loaded its tenant and
          capability context through the generated API client.
        </p>
      </section>
      <section aria-labelledby="next-capabilities-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Product roadmap</p>
            <h2 id="next-capabilities-title">Capability areas</h2>
          </div>
          <span className="badge">Extensible shell</span>
        </div>
        <div className="capability-grid">
          <article className="capability-card">
            <span className="capability-index">01</span>
            <h3>Schema workbench</h3>
            <p>
              Define and evolve document structures without fixed product
              fields.
            </p>
          </article>
          <article className="capability-card capability-card-muted">
            <span className="capability-index">02</span>
            <h3>Document intake</h3>
            <p>
              Receive, preserve, and inspect source documents in a trusted flow.
            </p>
          </article>
          <article className="capability-card capability-card-muted">
            <span className="capability-index">03</span>
            <h3>Review operations</h3>
            <p>
              Validate evidence, collaborate, and preserve attributable
              revisions.
            </p>
          </article>
        </div>
      </section>
    </div>
  );
}

function NotFound() {
  return (
    <main className="centered-page">
      <section className="status-card">
        <p className="eyebrow">Page not found</p>
        <h1>This route is not available.</h1>
        <p>Return to the authenticated Evidentia workspace.</p>
        <Link className="button button-primary" to="/app">
          Open overview
        </Link>
      </section>
    </main>
  );
}

function ApplicationRoutes({
  access,
  schemas,
  documents,
}: {
  readonly access: AccessClient;
  readonly schemas: SchemaClient;
  readonly documents: DocumentClient;
}) {
  return (
    <Routes>
      <Route path="/" element={<Navigate replace to="/app" />} />
      <Route path="/login" element={<LoginPage access={access} />} />
      <Route
        path="/select-tenant"
        element={<TenantSelectionPage access={access} />}
      />
      <Route
        path="/app"
        element={
          <ProtectedRoute access={access}>
            <ApplicationShell access={access} />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route
          path="documents"
          element={<DocumentIntakePage documents={documents} />}
        />
        <Route
          path="schemas"
          element={<SchemaWorkbenchPage schemas={schemas} />}
        />
        <Route
          path="schemas/:schemaId"
          element={<SchemaDraftEditorPage schemas={schemas} />}
        />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

/** Render the routed, authenticated Evidentia browser application.
 * @skyhook-implements REQ-012
 * @skyhook-implements NFR-002
 * @skyhook-implements NFR-005
 * @skyhook-story STORY-017
 */
export function App({
  access = browserAccessClient,
  schemas = browserSchemaClient,
  documents = browserDocumentClient,
  initialEntries,
}: AppProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          mutations: { retry: false },
          queries: { refetchOnWindowFocus: false },
        },
      }),
  );
  const application = (
    <QueryClientProvider client={queryClient}>
      <ApplicationRoutes
        access={access}
        schemas={schemas}
        documents={documents}
      />
    </QueryClientProvider>
  );

  if (initialEntries !== undefined) {
    return (
      <MemoryRouter initialEntries={[...initialEntries]}>
        {application}
      </MemoryRouter>
    );
  }
  return <BrowserRouter>{application}</BrowserRouter>;
}
