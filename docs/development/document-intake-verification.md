# Original document intake verification

This story proves that Evidentia can receive an original source, preserve its
bytes, and return tenant-scoped custody metadata. It intentionally does not
extract text, run OCR, classify content, render previews, or execute documents.
Scanned images are preserved as opaque originals; parsing and OCR belong to
later stories.

## Automated checks

From the repository root, run the fast, PostgreSQL-independent checks:

```sh
cd backend
uv run ruff check src/evidentia/modules/documents src/evidentia/entrypoints/api/documents.py tests/modules/documents
uv run mypy src/evidentia/modules/documents src/evidentia/entrypoints/api/documents.py
uv run pytest -q tests/modules/documents tests/integration/documents/test_document_migration_structure.py
cd ..
pnpm --filter @evidentia/typescript-sdk typecheck
pnpm --filter @evidentia/typescript-sdk test
pnpm --filter @evidentia/web typecheck
pnpm --filter @evidentia/web test
make generated-check
```

The native PostgreSQL API and repository tests require an explicitly enabled
local server and use disposable databases, not the ordinary `evidentia`
database:

```sh
make native-db-verify
cd backend
uv run pytest --postgres -q tests/api/documents tests/integration/documents
```

The integration fixture creates a unique `evidentia_test_<hex>` database,
migrates that database, then drops only that exact test-namespace database in a
`finally` block. It reads connection settings from `.env`, and uses the local
peer-authenticated role (override with `--postgres-admin-user` if necessary).
Never change the test database-name guard to target `evidentia` or another
developer database.

## Browser interaction

1. Ensure the local PostgreSQL service is running and `make native-db-verify`
   succeeds. If this is a fresh database, apply the already-approved migrations
   with `make db-upgrade`; that command changes the configured local database.
2. Start the API in one terminal with `make native-api` and the web app in
   another with `make native-web`.
3. Open the printed local web URL, sign in with the configured bootstrap
   account, and open **Documents** in the workspace navigation.
4. Choose a non-sensitive PDF, DOCX, JPEG, PNG, or TIFF sample and select
   **Preserve original**. The page should announce success and show the
   filename, `preserved` status, byte count, SHA-256 digest, and document ID.
5. In another tenant, the document ID must not resolve. A member with
   `documents.read` but without `documents.write` can open the page but must not
   see the file picker or upload action.
6. Restart the API and query the same document through `GET
/api/v1/documents/{document_id}` using the authenticated browser session (or
   reload and upload a separate sample). Custody metadata is PostgreSQL-backed;
   original bytes are in the configured artifact directory.

Use only disposable, non-sensitive samples for manual interaction. There is no
document deletion UI in this pass, so successful manual uploads remain in the
configured database and artifact directory until an explicitly managed local
cleanup. Do not remove the shared artifact root while the API may be using it.

## Expected rejection and failure behavior

- A file over `EVIDENTIA_STORAGE__MAXIMUM_UPLOAD_BYTES` returns a safe `413`;
  the default is 25 MiB.
- Unsupported media types return a safe `415`. The server does not trust the
  browser's `accept` attribute as an authorization or validation boundary.
- Missing/invalid session or CSRF proof is rejected by the existing access
  boundary; lacking `documents.write` is a `403`.
- Reusing an idempotency key for different bytes is a `409`; a matching retry
  converges on the preserved custody record.
- Storage failures return a sanitized `503`, while durable custody records the
  failed state. Routine events contain correlation/scope identifiers and a
  stable reason class, not document bytes, credentials, or storage paths.
- Client filenames are metadata only and never form part of the storage key.
  The local adapter writes atomically beneath a tenant-specific content address
  and verifies the SHA-256 before accepting existing bytes.

This pass treats accepted media as opaque bytes; a matching media type does
not prove that a file is structurally valid or safe to render. Do not open or
preview uploaded content in the application. Parsing, OCR, malware scanning,
and document inspection must be added behind separately governed providers.

## Troubleshooting

- `native-db-verify` reports connection refused: start the local PostgreSQL
  service, then rerun the read-only check. The test commands do not start
  services for you.
- PostgreSQL tests cannot authenticate as the admin role: use the supported
  local peer-authenticated account or explicitly pass
  `--postgres-admin-user <local-role>`; this is separate from the app's
  `evidentia` role.
- `503` while uploading: check that the configured artifact root is writable
  by the API process and that the filesystem has enough space.
- The generated-contract check changes files: rerun `make generate-api-contract`
  and review the OpenAPI and TypeScript diffs before committing.
