# Schema API verification

This runbook proves the governed schema lifecycle through the native API. For the
corresponding browser interaction, follow the
[Schema Workbench verification runbook](schema-workbench-verification.md).

## Automated proof

Keep native PostgreSQL running, then execute:

```sh
make native-db-verify
make schema-api-check
```

The check creates a uniquely named disposable database, applies all migrations, runs the
schema persistence and HTTP proofs, closes its connections, and drops it. It never clears
or recreates the ordinary `evidentia` database.

The HTTP proof covers:

| Concern            | Expected proof                                                                    |
| ------------------ | --------------------------------------------------------------------------------- |
| Primary lifecycle  | Login, create, list, replace, publish, and retrieve succeed                       |
| Validation         | Unknown core field types return `invalid_schema_definition`                       |
| Browser security   | Missing CSRF proof returns `csrf_rejected`                                        |
| Authentication     | Missing, expired, revoked, and invalid sessions return stable 401 responses       |
| Concurrent retry   | The same key and body produce one mutation and the same response                  |
| Concurrent editing | Two writes at one revision produce one success and one `schema_revision_conflict` |
| Durable retry      | A publish retry after API restart replays its original response                   |
| Pagination         | An opaque cursor traverses tenant drafts without duplication                      |
| Tenant isolation   | A selected second tenant cannot observe the first tenant's schema                 |
| Authorization      | A read-only membership receives `access_denied` for creation                      |
| Recovery           | Selecting the original tenant restores access without changing history            |
| Immutable history  | Editing the next draft does not alter the published snapshot                      |
| Sanitization       | Passwords and cookie names do not appear in response bodies                       |
| Correlation        | Each transport response carries its request correlation ID                        |

## Manual native-API journey

Prepare the ordinary local database once, then keep the API running in the first terminal:

```sh
make native-db-verify
make db-upgrade
make identity-init
make native-api
```

In a second terminal, enter the configured bootstrap identity. Silent password input keeps
the secret out of terminal output and shell history:

```sh
read -r "EVIDENTIA_LOGIN?Bootstrap login: "
read -s "EVIDENTIA_PASSWORD?Bootstrap password: "
echo
COOKIE_JAR=$(mktemp -t evidentia-schema-cookies)
trap 'rm -f "$COOKIE_JAR"' EXIT
```

Log in and capture the session and readable CSRF proof in the temporary cookie jar:

```sh
curl --fail-with-body --silent --show-error \
  --cookie-jar "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --header 'Origin: http://127.0.0.1:5173' \
  --data "$(jq -n --arg login "$EVIDENTIA_LOGIN" --arg password "$EVIDENTIA_PASSWORD" \
    '{login_identifier: $login, password: $password}')" \
  http://127.0.0.1:8000/api/v1/access/sessions | jq

unset EVIDENTIA_PASSWORD
CSRF_TOKEN=$(awk '$6 == "evidentia_csrf" {print $7}' "$COOKIE_JAR")
```

Create a dynamic draft with a retry key and retain the response identifiers:

```sh
CREATE_KEY="manual-create-$(uuidgen)"
CREATE_RESPONSE=$(curl --fail-with-body --silent --show-error \
  --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --header 'Origin: http://127.0.0.1:5173' \
  --header "X-CSRF-Token: $CSRF_TOKEN" \
  --header "Idempotency-Key: $CREATE_KEY" \
  --header 'X-Correlation-ID: manual-schema-create' \
  --data @docs/examples/schema-draft-create.json \
  http://127.0.0.1:8000/api/v1/schemas/drafts)

echo "$CREATE_RESPONSE" | jq
SCHEMA_ID=$(echo "$CREATE_RESPONSE" | jq -r .schema_id)
```

Expected result: HTTP 201 content shows revision `1`, version `1`, a server-generated
`schema_id`, and the canonical dynamic field. Repeating the exact request with the same
`CREATE_KEY` returns the same body and does not create another draft. Reusing the key with
different JSON returns HTTP 409 and `idempotency_key_reused`.

List and read the stored draft:

```sh
curl --fail-with-body --silent --show-error --cookie "$COOKIE_JAR" \
  'http://127.0.0.1:8000/api/v1/schemas/drafts?limit=25' | jq

curl --fail-with-body --silent --show-error --cookie "$COOKIE_JAR" \
  "http://127.0.0.1:8000/api/v1/schemas/drafts/$SCHEMA_ID" | jq
```

Replace revision 1 and publish revision 2:

```sh
REPLACE_KEY="manual-replace-$(uuidgen)"
jq '. + {expected_revision: 1}' docs/examples/schema-draft-create.json | \
  curl --fail-with-body --silent --show-error \
    --cookie "$COOKIE_JAR" \
    --header 'Content-Type: application/json' \
    --header 'Origin: http://127.0.0.1:5173' \
    --header "X-CSRF-Token: $CSRF_TOKEN" \
    --header "Idempotency-Key: $REPLACE_KEY" \
    --data-binary @- \
    "http://127.0.0.1:8000/api/v1/schemas/drafts/$SCHEMA_ID" | jq

PUBLISH_KEY="manual-publish-$(uuidgen)"
curl --fail-with-body --silent --show-error \
  --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --header 'Origin: http://127.0.0.1:5173' \
  --header "X-CSRF-Token: $CSRF_TOKEN" \
  --header "Idempotency-Key: $PUBLISH_KEY" \
  --header 'X-Correlation-ID: manual-schema-publish' \
  --data '{"expected_revision":2}' \
  "http://127.0.0.1:8000/api/v1/schemas/drafts/$SCHEMA_ID/publications" | jq
```

Expected publication result: immutable version `1` is returned, its correlation ID is
`manual-schema-publish`, and the working draft advances to version `2`, revision `3`.

Retrieve the immutable snapshot:

```sh
curl --fail-with-body --silent --show-error --cookie "$COOKIE_JAR" \
  "http://127.0.0.1:8000/api/v1/schemas/$SCHEMA_ID/versions/1" | jq
```

For restart durability, stop `make native-api` with Ctrl-C, start it again, then rerun the
publication request with the same `PUBLISH_KEY` and body. The session remains valid and
the original HTTP 201 publication response is replayed. A new key with stale revision `2`
instead returns `schema_revision_conflict`.

## Current limitations

- Advanced JSON import/export and configuration for extension types remain deferred;
  the current workbench preserves server-provided advanced configuration but only creates
  types that have safe visual defaults.
- Artifact-bound schemas fail publication until the governed artifact catalog is
  integrated. This is fail-closed behavior: client-supplied artifact digests are not
  treated as authority.
- Tenant creation and membership management do not yet have administrator screens. The
  automated proof creates a second read-only tenant only inside its disposable database.

## Troubleshooting

- `connection refused`: keep `make native-api` running and verify port 8000.
- `session_required`: log in again; the temporary cookie jar is missing or expired.
- `csrf_rejected`: recalculate `CSRF_TOKEN` after every login or tenant rotation.
- `origin_rejected`: use the configured local web origin exactly, including scheme/port.
- `schema_revision_conflict`: GET the draft again and submit its current revision.
- `idempotency_key_reused`: generate a new key for different command content.
- PostgreSQL test permission failure: grant the operating-system PostgreSQL role
  `CREATEDB`, or pass `--postgres-admin-user=postgres` to the pytest command.

@skyhook-implements REQ-003
@skyhook-implements REQ-012
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements NFR-008
@skyhook-story X51S43NTMRW5ASYSKJBF7FW845
