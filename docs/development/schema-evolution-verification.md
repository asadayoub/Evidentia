# Schema evolution verification

This runbook proves portable schema export, import inspection, deterministic comparison,
and safe draft evolution through the native application. Docker is not required.

## Automated proof

Keep native PostgreSQL 16 running, then execute:

```sh
make native-db-verify
make schema-evolution-check
```

The check creates a uniquely named disposable PostgreSQL database, applies migrations,
and drops it in guaranteed teardown. It never clears, migrates, or writes to the ordinary
`evidentia` development database. It also verifies the domain contracts, deterministic
OpenAPI and generated SDK, browser interactions, accessibility checks, and production web
build.

The proof covers:

| Concern       | Expected evidence                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------------------- |
| Export        | Draft and immutable publication packages use deterministic versioned JSON envelopes                     |
| Validation    | Malformed, unsupported, unknown-core-type, and packages over 1 MiB fail before mutation                 |
| Preview       | New-target previews make no false compatibility claim; existing targets report ordered changes          |
| Comparison    | Changes classify as additive-compatible, behavior-changing, or breaking with stable paths and codes     |
| Authority     | Imported identity is provenance; new identity, tenant, actor, revision, and version remain server-owned |
| Apply         | New imports create a draft; existing imports require the observed revision                              |
| Concurrency   | A stale import returns `schema_revision_conflict` without overwriting newer state                       |
| Retry/restart | An idempotency key replays the original result across a fresh API instance                              |
| Isolation     | A second tenant cannot preview or apply against another tenant's draft                                  |
| History       | Applying a package never changes an immutable published snapshot                                        |
| Safety        | Responses omit passwords/cookies and events contain digest metadata instead of package content          |

## Run the browser application

Prepare the existing native development database if needed:

```sh
make native-db-verify
make db-upgrade
make identity-init
```

This story adds no migration. If your database was already current, `make db-upgrade`
has nothing new to apply.

Start the API and frontend in separate terminals:

```sh
make native-api
```

```sh
make native-web
```

Open `http://127.0.0.1:5173`, sign in, and select **Schemas**.

## Export and create-from-package journey

1. Open an existing schema draft. If none exists, create and save one first.
2. In **Portable schema package**, select **Export draft JSON**.
3. Confirm the downloaded filename identifies the schema, snapshot kind, and version.
4. Open the file in a text editor. It must have format `evidentia.schema-draft`, envelope
   version `1`, source identity/version, and canonical dynamic content. It must not contain
   a tenant ID, credential, session, cookie, or database representation.
5. Return to **Schemas**. Under **Import a schema**, choose the exported JSON file.
6. Select **Preview changes**. Confirm the preview says a new server-owned identity will
   be allocated and shows the source version and abbreviated package digest.
7. Select **Create draft from package**. Confirm the browser opens a different schema ID
   with the same editable content.

## Compare and update an existing draft

1. Open the target draft and save any unsaved work.
2. Choose a canonical draft or publication JSON package in **Compare and import**.
3. Select **Preview changes**.
4. Review every path-specific change and its classification:
   - `additive compatible` means an optional field was added;
   - `behavior changing` includes relaxed constraints, changed configuration, modules, or
     artifact bindings;
   - `breaking` includes required additions, removals, type changes, and tightened
     cardinality.
5. Select **Apply to this draft** only after reviewing the preview. Confirm the revision
   increases while the target schema identity remains unchanged.
6. Save/export again if desired. Publication remains a separate explicit action and still
   requires acknowledgement for behavior-changing or breaking changes.

After at least one publication, the editor also offers **Export published vN**. Importing
that package creates or updates a working draft; it never rewrites the publication.

## Concurrency and recovery

Open one target draft in two tabs:

1. Preview a package in the second tab.
2. Save or apply a different change in the first tab.
3. Apply the previously previewed package in the second tab.
4. Confirm the operation reports a revision conflict and does not overwrite the first
   tab. Reload the current draft, preview again, and only then apply.

To check transport recovery, stop the API before preview or apply. The page must show a
safe error without package contents or internal details. Restart `make native-api` and
retry. A command that reached the server can be safely replayed by its idempotency key;
the automated proof verifies this across a fresh application instance.

## Accessibility inspection

- Complete file selection, preview review, apply, and export using only the keyboard.
- Confirm the file input and buttons have distinct announced labels.
- Confirm validation and service errors use alert semantics and do not rely on color.
- Confirm the preview status is announced and every change includes text for path,
  explanation, and severity.
- At 200% zoom and narrow width, the file row and actions must wrap without clipping.

## Intentional limits

- Only canonical Evidentia draft/publication envelope version 1 is supported. Future
  envelope versions must receive an explicit compatibility implementation.
- Packages are limited to 1 MiB at both browser and API boundaries.
- Recognized extension definitions are preserved as inert configuration; importing a
  package does not install or activate extension code.
- Preview is intentionally ephemeral. Long-lived approvals, resumable bulk imports, and
  import job history would justify a dedicated aggregate and migration later.
- Import changes working drafts only. Record migration/reprocessing requires a separate
  explicit revision workflow and is never triggered automatically.
- The UI presents a change list rather than a full side-by-side JSON diff or published
  version catalog.

## Troubleshooting

- **Invalid package:** confirm the file is UTF-8 JSON with `evidentia.schema-draft` or
  `evidentia.schema` format and envelope version `1`.
- **Package too large:** reduce the package below 1 MiB; do not split one schema across
  unrelated imports.
- **Revision conflict:** reload the target, preview against the new revision, and reapply.
- **Access denied:** read is required for export/preview and write is required for apply.
- **Artifact-bound package rejected at publication:** referenced artifacts remain
  fail-closed until the governed artifact catalog confirms their version and digest.
- **PostgreSQL test permission failure:** grant the operating-system PostgreSQL role
  `CREATEDB`, or pass `--postgres-admin-user=postgres` to the pytest command.

@skyhook-implements REQ-003
@skyhook-implements REQ-016
@skyhook-implements REQ-017
@skyhook-implements NFR-001
@skyhook-implements NFR-005
@skyhook-implements NFR-008
@skyhook-story STORY-018
