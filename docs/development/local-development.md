# Local development

## Native PostgreSQL workflow

Evidentia currently supports native PostgreSQL 16.x for ordinary development. Docker is optional and its equivalent development profile is deferred to `TASK-008` near the end of product development.

Generate a private environment file once:

```sh
make local-init
```

The generator refuses to overwrite an existing `.env`. If the file predates the native workflow, preserve any values you need, move it aside, and run `make local-init` again. Never commit `.env`.

Existing environments can receive newly required settings without replacing their database password or any other configured value:

```sh
make local-env-upgrade
```

The upgrade is atomic, refuses symlink targets, adds only missing keys, restores owner-only `0600` permissions, and is safe to repeat. It generates a random local bootstrap password and a separate 256-bit session secret without printing either value.

Fresh and upgraded local environments define the initial identity as `admin@localhost` in the `local` tenant. These are configuration defaults, not automatically created accounts. The explicit `make identity-init` command consumes them to create the first tenant and administrator; ordinary API startup never creates or replaces that identity.

Start and inspect Homebrew PostgreSQL:

```sh
brew services start postgresql@16
brew services info postgresql@16
```

Create the dedicated `evidentia` login and database, then verify the exact configured connection:

```sh
make native-db-init
make native-db-verify
```

Initialization is idempotent: it creates missing local objects, retains an existing database, and aligns the dedicated development role password with the private `.env`. It does not run application migrations.

Apply all module-owned migrations after initialization:

```sh
make db-upgrade
```

Create the configured first tenant and administrator after migrations are current:

```sh
make identity-init
```

The command creates the tenant, operator, membership, administrator capability grants,
and local Argon2id credential in one transaction. Repeating it with exactly the same
configuration is safe and reports that the identity is already initialized. It fails
closed if matching tenant or login names are attached to different state, if capabilities
or display names differ, or if the configured password does not match the stored hash.
It never prints the password or its hash.

During unreleased migration development, verify reversibility with `make db-downgrade` followed by `make db-upgrade`. Once a migration has shipped, its file is append-only and corrections use a new forward migration.

PostgreSQL integration tests are deliberately opt-in:

```sh
make postgres-test
```

Fast repository checks use the configured dedicated database and roll back every write. Durability checks create a uniquely named `evidentia_test_<random>` database, apply all migrations, commit and reload records through fresh connections, then terminate its connections and drop it in guaranteed teardown. The main `evidentia` database is never cleared or recreated.

Disposable database setup defaults to the current operating-system username and requires that local peer-authenticated PostgreSQL role to have `CREATEDB`. Override only the administrative role name when necessary:

```sh
uv run pytest --postgres --postgres-admin-user=postgres backend/tests/integration
```

The harness refuses to drop names outside the `evidentia_test_<16 hex characters>` namespace and verifies that teardown completed. Docker/Testcontainers will provide the equivalent disposable server path when the deferred hybrid profile is implemented.

## Run and inspect the access API

After PostgreSQL is ready, migrations are current, and `make identity-init` has
created or validated the configured administrator, start the native API:

```sh
make native-db-verify
make db-upgrade
make identity-init
make native-api
```

`native-api` loads the ignored `.env` through the same validated Pydantic settings
used by the application. It does not source the file in the shell or print any
credential. The default API address is `http://127.0.0.1:8000`.

In a second terminal, start the native browser development server:

```sh
make native-web
```

`native-web` uses the locked pnpm workspace and the Vite configuration committed
with the frontend. It binds to `http://127.0.0.1:5173`, which is already included
in the API's explicit credentialed-CORS development origins. Keep `native-api`
running in the first terminal so login and protected routes can restore their
server-owned session.

Open `http://127.0.0.1:8000/docs` and use the access operations in this order:

1. Run `POST /api/v1/access/sessions` using the configured bootstrap login and
   password. The browser stores the opaque session in an HttpOnly cookie; the
   response body never contains it.
2. Run `GET /api/v1/access/context`. It returns the current operator, tenant,
   membership, capabilities, session identifier, and correlation identifier.
3. To test tenant rotation, copy the non-HttpOnly `evidentia_csrf` cookie value
   from the browser's developer-tools cookie view into the operation's
   `X-CSRF-Token` header, then run `PUT /api/v1/access/session/tenant` with an
   available tenant ID returned by login. The bearer cookie rotates and the old
   token becomes invalid immediately.
4. Supply the current CSRF value to `DELETE /api/v1/access/session`. A later
   context request returns the sanitized `session_invalid` response.

For a restart-durability check, log in, stop `make native-api` with Ctrl-C, start
it again, and request the current context in the same browser. The database-backed
session remains valid until idle/absolute expiry or explicit revocation. Logout
remains revoked across another restart.

Local HTTP permits `COOKIE_SECURE=false`. Production configuration fails closed
unless secure cookies are enabled. Credentialed CORS accepts only explicitly
configured origins, and cookie-authenticated mutations require both a trusted
origin and the session-bound CSRF proof.

Bootstrap, origin rejection, login, context denial, tenant selection/rotation,
and logout emit structured `security_event` records. Successful lifecycle events
carry the applicable operator, tenant, session, and correlation identifiers;
denials carry stable reason codes. Login attempts use a one-way identifier
fingerprint instead of logging the supplied login name. Passwords, raw session
tokens, credential material, and authorization values are never event fields and
remain covered by the logging formatter's defensive redaction.

The full automated equivalent uses uniquely named disposable databases and does
not alter the ordinary `evidentia` database:

```sh
make postgres-test
```

Stop the database when desired:

```sh
brew services stop postgresql@16
```

## Connection contract

The application reads `EVIDENTIA_DATABASE__HOST`, `PORT`, `NAME`, `USER`, `PASSWORD`, `CONNECT_TIMEOUT_SECONDS`, `SSLMODE`, and `APPLICATION_NAME`. Local defaults use `127.0.0.1:5432`, database `evidentia`, role `evidentia`, and `sslmode=prefer`. Secrets are generated into the owner-readable ignored `.env` and are never printed by the readiness command.

## Identity and session configuration

Local bootstrap identity uses `EVIDENTIA_IDENTITY__BOOTSTRAP_LOGIN_IDENTIFIER`, `BOOTSTRAP_DISPLAY_NAME`, `BOOTSTRAP_TENANT_SLUG`, `BOOTSTRAP_TENANT_NAME`, and `BOOTSTRAP_PASSWORD`. The password is optional for ordinary process startup but will be required by the explicit identity bootstrap command. If configured, it must contain at least 16 characters and cannot be a recognized placeholder.

Opaque browser sessions use `EVIDENTIA_SESSION__SECRET`, `IDLE_TIMEOUT_SECONDS`, `ABSOLUTE_TIMEOUT_SECONDS`, `COOKIE_NAME`, `COOKIE_SECURE`, and `COOKIE_SAMESITE`. The defaults are a 30-minute idle timeout and a 12-hour absolute lifetime. Local HTTP development permits `COOKIE_SECURE=false`; production fails closed unless a secret of at least 32 characters is supplied and secure cookies are enabled.

The committed `.env.example` contains placeholders only. Deployment environments must inject database, bootstrap, and session secrets through their secret manager rather than copying local values. Session termination uses the persisted revocation workflow; never attempt to rotate credentials by editing database rows manually.

After successful provisioning, remove the bootstrap password from the runtime environment
or rotate it to a separately protected recovery value. Ordinary API and worker startup do
not need this password. Password rotation for an existing administrator is intentionally
not performed by `identity-init`: use the dedicated recovery/credential-rotation workflow
when that capability is implemented. Changing the configured bootstrap password and
re-running this command produces a conflict instead of silently replacing a credential.

## Troubleshooting

If Homebrew reports an error, inspect before changing anything:

```sh
brew services info postgresql@16
pg_isready --host=127.0.0.1 --port=5432
tail -n 100 /usr/local/var/log/postgresql@16.log
```

A `postmaster.pid already exists` message can mean either a live server or a stale file after an unclean shutdown. Confirm the recorded PID is not PostgreSQL, confirm no socket or listener exists, and use `pg_ctl status` before moving the PID file. Never delete the data directory or run `initdb` over it as a repair.

The stale PID encountered on 2026-10-03 was moved recoverably to `/tmp/evidentia-stale-postmaster.pid-20261003`; PostgreSQL performed automatic WAL recovery and returned to a ready state without data deletion.
