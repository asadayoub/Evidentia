# Authenticated application shell verification

This runbook proves the first real Evidentia browser journey without Docker. It
covers the generated TypeScript API boundary, server-owned session restoration,
tenant and capability context, failure recovery, logout, and the native
PostgreSQL persistence boundary.

## Automated proof

Start native PostgreSQL 16 and confirm that the operating-system PostgreSQL role
used by the test harness can create disposable databases. Then run:

```sh
make native-db-verify
make authenticated-shell-check
```

The proof performs three independent checks:

1. regenerates and compares the OpenAPI and TypeScript SDK artifacts;
2. runs browser interaction and automated accessibility checks in jsdom;
3. creates a uniquely named `evidentia_test_<random>` database, applies the
   current migrations there, exercises the real access API, and drops that
   database in guaranteed teardown.

The command never clears or recreates the ordinary `evidentia` database. The
PostgreSQL test covers login, origin and CSRF rejection, trusted context,
cross-tenant denial, tenant rotation, token invalidation, restart durability,
forced expiry, logout durability, stable errors, correlation identifiers,
security-event attribution, and absence of credentials or raw tokens from
responses, storage, and events.

## Manual browser journey

### Prepare once

Use the native workflow if it has not already been prepared:

```sh
make local-init
make native-db-init
make native-db-verify
make db-upgrade
make identity-init
```

`make db-upgrade` changes schema state, so inspect pending migrations first when
working with any database that contains valuable data. `make identity-init` is
idempotent and refuses to replace a conflicting identity. Read the ignored,
owner-only `.env` locally to obtain the configured
`EVIDENTIA_IDENTITY__BOOTSTRAP_LOGIN_IDENTIFIER` and
`EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD`; do not paste either value into logs,
commits, screenshots, or issue trackers.

### Run the application

In terminal one:

```sh
make native-api
```

In terminal two:

```sh
make native-web
```

Open `http://127.0.0.1:5173/app` in a current browser. Expected results:

1. A signed-out browser is redirected to `/login`; protected workspace content
   is not rendered.
2. An incorrect password produces the generic credential error and does not
   reveal whether the identifier exists.
3. The configured local identity opens `/app`. The header shows the trusted
   operator and tenant names returned by the API, not values supplied by the
   browser.
4. The navigation exposes only routes allowed by the returned capabilities.
   The initial administrator can open **Schemas**, whose current page is an
   intentional placeholder for the next schema story.
5. Reloading `/app/schemas` restores the HttpOnly-cookie session and remains on
   the requested route. No bearer token appears in local storage, session
   storage, the page, or API response bodies.
6. Stop the API with Ctrl-C and reload. The browser shows a recoverable service
   error. Restart `make native-api`, select **Try again**, and the workspace
   loads without a new login.
7. Restart the API once more while the browser session is active. Reloading the
   page restores the database-backed session.
8. Select **Sign out**. The application returns to `/login`, protected content
   disappears, and reloading does not restore the revoked session.

Use keyboard-only navigation for the same journey. Focus must reach the login
fields, submit button, primary navigation links, and sign-out button in a
logical order; visible focus must remain present. At 200% browser zoom, the
page must remain usable without obscured controls. These real-layout checks
complement the automated axe scan because jsdom cannot measure color contrast,
zoom, layout, or visual focus.

### Optional tenant-selection state

The tenant chooser appears only when an authenticated operator has more than
one eligible membership and no active tenant. Creating additional tenants and
memberships is not yet a browser capability. Use governed administration or
test fixtures rather than manually editing database rows. The automated suite
proves that an allowed choice establishes trusted tenant context and a
cross-tenant choice is rejected.

## Troubleshooting

- **API connection error:** confirm `make native-api` is running at
  `http://127.0.0.1:8000` and use **Try again** after it becomes ready.
- **Browser origin rejected:** use exactly `http://127.0.0.1:5173`; `localhost`
  is a different origin unless explicitly configured.
- **Login always fails:** rerun `make identity-init` and read its conflict-safe
  result. Confirm the identifier and password from the same private `.env` used
  by `make native-api`.
- **Database unavailable:** run `make native-db-verify`. This validates the
  configured dedicated database and role without applying migrations.
- **Schema is behind:** stop and inspect migration state before choosing to run
  `make db-upgrade`; migration execution is intentionally a separate action.
- **Port already in use:** stop the existing local process using port 8000 or
  5173 rather than starting a second instance with an undocumented origin.
- **Cookies appear absent:** local development intentionally uses
  `COOKIE_SECURE=false` over loopback HTTP. Production configuration requires
  secure cookies and HTTPS.

## Current boundary

This pass proves the shell through focused browser interaction tests, a real
API backed by disposable PostgreSQL, and the manual current-browser journey.
Automated Playwright cross-browser execution remains part of the later layered
CI and journey-test capability; it is not represented here as already
implemented. Password recovery, OIDC/SSO, browser-based tenant administration,
and the schema workbench are also later stories, not missing behavior in this
shell pass.
