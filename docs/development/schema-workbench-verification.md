# Schema Workbench verification

The Schema Workbench is the first complete browser path for creating, editing, and
publishing governed dynamic schemas. It uses the generated TypeScript SDK and the same
tenant-authorized API proven by the schema API tests; the browser does not invent tenant,
operator, schema identity, revision, or publication authority.

## Automated proof

Keep native PostgreSQL 16 running, then execute:

```sh
make native-db-verify
make schema-workbench-check
```

The check creates a uniquely named disposable PostgreSQL database, applies migrations,
proves the authenticated schema API and persistence behavior, drops the database in
guaranteed teardown, runs browser interaction and accessibility tests, and builds the
production frontend. It does not clear, migrate, or write to the ordinary `evidentia`
database.

The combined proof covers:

| Concern           | Evidence                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------- |
| Primary journey   | Login/API create, list, edit, publish, and retrieve plus browser create, edit, save, and publish                    |
| Dynamic structure | Registry-driven scalar types and recursive object, array, and table structures                                      |
| Validation        | Invalid keys, duplicate keys, invalid cardinality, unknown stored types, and empty publication                      |
| Authority         | Server-issued identity/revision and capability-controlled create, write, and publish controls                       |
| Concurrency       | Optimistic revision conflicts preserve browser edits and offer an explicit current-revision reload                  |
| Retry and restart | Idempotent API replay survives a new application instance without duplicating mutations                             |
| Isolation         | Cross-tenant reads and writes fail while returning to the original tenant restores access                           |
| History           | Published snapshots remain immutable while the next working draft advances                                          |
| Safety            | Stable client errors, correlation identifiers, CSRF enforcement, and secret-free response bodies                    |
| Accessibility     | Semantic headings, labels, fieldsets, live notices, alert states, keyboard-native controls, and automated axe scans |

## Prepare the native application

Docker is not required. The ordinary development database is used only for the manual
journey and is never recreated by these commands.

Run once, or whenever migrations/bootstrap configuration changes:

```sh
make native-db-verify
make db-upgrade
make identity-init
```

`make db-upgrade` changes the configured development database schema, so inspect pending
migrations first when preserving existing data matters. `make identity-init` is
idempotent and never prints the configured password.

Start the API in one terminal:

```sh
make native-api
```

Start the browser application in another:

```sh
make native-web
```

Open `http://127.0.0.1:5173` and sign in with the bootstrap identity stored in the local,
ignored `.env` file.

## Manual browser journey

1. Select **Schemas** in the application navigation. Confirm the page either lists the
   current tenant's drafts or shows the empty state. No create button appears for a
   read-only membership.
2. Select **Create schema** (or **Create your first schema**). Confirm the URL changes to
   `/app/schemas/<server-generated-id>` and the editor reports version 1, revision 1.
3. Set the release label to `Invoice intake`.
4. Enter `invoice_number`, choose **Text**, and select **Add field**. Mark the field
   **Required**.
5. Add `supplier` as an **Object**. In its nested field group, add `name` as **Text**.
6. Add `line_items` as a **Table**, then add `description` as **Text** and `quantity` as
   **Integer** within its table columns. Confirm nested controls remain reachable with
   Tab and their visible labels describe the correct group.
7. Temporarily change a key to `Invalid key`. Confirm **Resolve before saving** appears
   and both save and publication remain unavailable. Restore a lowercase snake-case key.
8. Select **Save draft**. Confirm the saved notice announces a newer revision and
   **Unsaved changes** becomes **Saved**.
9. Select **Publish version 1**, review the immutable-action explanation, optionally add
   an acknowledgement, and select **Confirm version 1**. Confirm the notice reports
   version 1 published and the working draft advances to version 2.
10. Return to **Schemas**, reopen the draft, and confirm the saved dynamic structure is
    restored from PostgreSQL.

The manual journey creates real development records. Use a clearly recognizable label;
draft deletion is intentionally unavailable until governed retention/deletion behavior is
implemented.

## Conflict and recovery check

Open the same draft in two browser tabs:

1. Change and save the release label in the first tab.
2. Make a different local edit in the second tab and select **Save draft**.
3. Confirm the second tab reports **This draft changed elsewhere**, retains its unsaved
   inputs, and does not overwrite the first tab.
4. Select **Reload current draft**. Confirm the server revision replaces the local copy.
   Reapply the intended change and save it against that current revision.

To check transport recovery, stop `make native-api`, reload the schema list, and confirm a
safe unavailable state with **Try again**. Restart the API and select **Try again**. The
page must recover without exposing a stack trace, database detail, cookie value, or other
secret.

## Accessibility inspection

Complete the journey once without a pointer:

- Tab order reaches navigation, create, field controls, save, and publication review in
  visual order.
- Every input and selector has an announced label; nested groups are announced as
  fieldsets.
- Focus indicators remain visible, status changes are announced, and errors do not rely
  on color alone.
- At 200% browser zoom and at a narrow viewport, controls wrap without horizontal page
  scrolling or clipped actions.

Automated axe checks supplement this inspection but do not replace keyboard and screen
reader review.

## Current intentional limits

- Direct visual creation is limited to field types with safe defaults. Extension fields,
  complex references, artifact bindings, and advanced type configuration require the
  later advanced editor/import workflow.
- The workbench lists the first 100 drafts. Cursor navigation/search belongs with the
  later schema-catalog experience; the API already exposes opaque cursor pagination.
- Published-version browsing and comparisons are planned separately. Publication is
  already immutable and retrievable through the API.
- Realtime collaborative presence is not part of this pass. Optimistic revision checks
  are authoritative; Firebase versus sockets remains a later decision if live
  collaboration becomes necessary.

## Troubleshooting

- **Cannot connect:** confirm `make native-api` is listening on port 8000 and
  `make native-web` is using port 5173.
- **Sign-in fails:** rerun `make identity-init` only after confirming `.env` still contains
  the intended bootstrap identity. It will not replace a mismatched existing credential.
- **Schema access unavailable:** the selected membership needs `schemas.read`; creation,
  editing, and publication additionally require their corresponding capabilities.
- **Origin or CSRF rejection:** access the committed local web origin exactly and avoid
  proxying it through an unconfigured hostname.
- **Revision conflict:** reload the current draft in the conflict banner, then reapply the
  retained local intent.
- **PostgreSQL test permission failure:** grant the operating-system PostgreSQL role
  `CREATEDB`, or pass `--postgres-admin-user=postgres` to the pytest command.

@skyhook-implements REQ-003
@skyhook-implements REQ-012
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements NFR-005
@skyhook-implements NFR-008
@skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
