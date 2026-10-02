# Canonical Revision Snapshot Contract

Status: Accepted  
Contract name: `evidentia.authorization-snapshot`  
Contract version: `1`  
Canonicalization: RFC 8785 JSON Canonicalization Scheme (`jcs-rfc8785`)  
Initial digest: SHA-256  
Skyhook story: `HKDJB0N3JTKZ2RRFRP5PT70PF9`

## Purpose

An authorization must bind to the exact tenant, record revision, material record content, action, and destination scope that a reviewer considered. This contract defines one cross-language payload that can be stored, hashed, submitted, verified, retried, and audited by Evidentia, local approval, optional Delibera integration, and destination delivery.

The canonical payload is dynamic and schema-driven. It contains no built-in invoice field list.

## Stored snapshot envelope

The stored envelope separates hashed authorization content from operational metadata:

```json
{
  "snapshot_id": "snp_opaque_id",
  "created_at": "2026-10-01T12:00:00.000Z",
  "payload": {
    "contract": "evidentia.authorization-snapshot",
    "version": "1",
    "canonicalization": "jcs-rfc8785",
    "tenant_id": "ten_opaque_id",
    "record": {
      "record_id": "rec_opaque_id",
      "revision_id": "rev_opaque_id",
      "revision_number": "3",
      "schema_id": "sch_opaque_id",
      "schema_version": "7"
    },
    "action": {
      "type": "record.authorize",
      "external_reference": "tenant-controlled-reference",
      "destination": {
        "configuration_id": "dst_opaque_id",
        "mapping_version": "4",
        "operation": "create-payable-record"
      }
    },
    "material": {
      "dynamic_field_key": "schema-normalized-value"
    }
  },
  "digest": {
    "algorithm": "sha-256",
    "encoding": "base64url-no-padding",
    "value": "digest-value"
  }
}
```

Only `payload` is canonicalized and hashed. `snapshot_id`, `created_at`, and the `digest` object are stored with the snapshot but are not part of the digest input. They cannot be substituted during verification because the persisted snapshot record binds them to the exact stored payload and digest.

## Digest procedure

1. Build `payload` from persisted, immutable, versioned inputs.
2. Reject duplicate object keys, non-I-JSON values, non-finite numbers, binary floating-point business values, invalid identifiers, or unsupported type encodings.
3. Serialize `payload` as UTF-8 bytes using RFC 8785 JCS.
4. Compute SHA-256 over those exact bytes.
5. Encode the 32-byte digest using unpadded base64url.
6. Persist the parsed payload, the exact canonical UTF-8 bytes or a byte-for-byte recoverable representation, the algorithm identifiers, and the digest in one transaction.
7. Verification rebuilds or reads the payload, repeats the version-selected procedure, compares digest bytes in constant time where relevant, and then verifies tenant, revision, action, policy, and current lifecycle guards.

Ordinary `json.dumps`, `JSON.stringify`, ORM serialization, field insertion order, pretty printing, or transport-body formatting is never treated as canonical serialization.

## Canonical type encodings

### Missing and null

- A missing field is absent from its containing object.
- An explicitly unknown or empty value may be `null` only when the published schema permits it.
- Missing and `null` are materially different.

### Strings

- Strings contain the exact Unicode scalar sequence produced by the versioned schema-normalization rule.
- JCS does not perform Unicode normalization. A schema that needs NFC, case folding, whitespace normalization, or identifier cleanup must define and version that transformation before snapshot construction.
- Raw source text and normalized material values remain separate; raw evidence is not silently substituted for the normalized value.

### Decimals and money

- Monetary values and arbitrary-precision decimals are JSON strings, never JSON numbers.
- The canonical decimal grammar is `-?(0|[1-9][0-9]*)(\.[0-9]+)?`.
- Exponents, leading plus signs, leading integer zeroes, trailing fractional zeroes, and negative zero are prohibited in canonical decimal values.
- Zero is encoded as `"0"`.
- Money is encoded as an object such as `{ "amount": "123.45", "currency": "USD" }`.
- Currency uses the schema-defined canonical identifier. The snapshot contract does not assume one currency catalog permanently.
- The source representation and any scale needed for evidence remain outside or alongside the normalized material value as defined by the schema.

### Integers

- Counters or bounded protocol integers may use JSON numbers only when the contract explicitly defines their safe range.
- Business identifiers, revision numbers, and arbitrary-size integers use canonical strings to avoid Python and JavaScript precision differences.

### Dates and instants

- Calendar dates use `YYYY-MM-DD` after schema-defined interpretation.
- Material instants use UTC RFC 3339 form with uppercase `T` and `Z` and exactly three fractional-second digits: `YYYY-MM-DDTHH:mm:ss.sssZ`.
- Ambiguous local dates or times cannot enter an authoritative snapshot until the schema workflow resolves them.

### Booleans

- Booleans use JSON `true` or `false`, never strings or numeric substitutes.

### Arrays

- Array order is material by default.
- If a schema defines set semantics, its versioned normalization rule must sort elements deterministically before snapshot construction.
- Line items retain explicit stable row identity and schema-defined order.

### Objects

- Objects contain only schema- or contract-defined keys.
- JCS determines serialized property order.
- Unknown extraction output remains raw provider output or an unmapped field candidate and cannot enter `material` until a published schema version defines it.

## Material field selection

The published schema and authorization policy determine material scope:

- A schema may mark fields or structures as always material for an action type.
- A workflow or authorization policy may add material context such as validation overrides, external references, document relationships, or destination operation details.
- A policy cannot remove schema-required material fields.
- Destination configuration identity, mapping version, and operation are included whenever changing them could alter the authorized effect.
- Comments, UI preferences, assignments, transient confidence scores, processing metrics, and non-authorizing evidence presentation are excluded unless a published policy explicitly makes them material.
- Evidence references may be included when the authorization policy requires the reviewer to authorize a particular source basis. Otherwise the immutable revision retains them outside `material` and the payload binds to the revision that owns them.

The material-selection rule and its version are retained with the approval submission even when the rule identifier is not itself inside `payload`.

## Construction invariants

- The payload is built only from a persisted immutable `RecordRevision`, published `SchemaVersion`, resolved module versions, and persisted destination/action scope.
- Tenant ID comes from trusted aggregate context.
- The builder cannot read mutable live external data without first capturing a versioned snapshot or reference governed by the schema-resolution contract.
- The revision ID, schema version, action type, and material object are required.
- Destination is omitted only when the authorization has no destination-specific effect.
- A snapshot is created once. Retries reuse the stored payload and digest rather than rebuilding them from current state.
- The snapshot and approval submission are committed atomically, or through a recoverable local transaction/outbox boundary that cannot submit an unpersisted snapshot.

## Idempotency and retries

- Submission uses a stable idempotency key scoped to tenant, approval adapter, client, and logical submission operation.
- Retrying the same logical submission uses the same idempotency key, exact stored payload, and digest.
- The same key with a different payload or digest is a conflict.
- If an adapter accepts the request but the response is lost, reconciliation retrieves the original request rather than creating a replacement.
- Callback or polling results are applied only after matching tenant, external request ID, revision ID, payload digest, action, and aggregate version.

## Changes, supersession, and resubmission

- Any change to `payload` produces a new digest.
- A material record change requires a new `RecordRevision`, snapshot, and approval submission.
- An action, destination, mapping, or other authorization-scope change requires a new snapshot and submission even when record field values are unchanged.
- Non-material comments or presentation changes do not alter the snapshot.
- A rejected or changes-requested submission remains immutable and terminal. Corrected content creates a child revision and a new linked submission.
- A pending request for older content may be cancelled or allowed to reach a historical outcome under policy, but it can never authorize a newer revision.
- A later approved revision supersedes current authority for the earlier revision according to workflow policy without erasing the earlier decision.
- A canonicalization, digest, material-selection, or schema version change does not reinterpret an existing snapshot. Existing decisions continue to verify with their recorded versions. New submissions use the configured current versions.
- Multiple active approval submissions for the same tenant, revision, action, and destination scope are prohibited unless an explicit replacement or multi-policy workflow models them separately.

## Verification before delivery

Immediately before delivery, Evidentia verifies:

1. the stored canonical payload reproduces the stored digest under its recorded versions;
2. the authorization decision references the same tenant, request, revision, and digest;
3. the action, destination configuration, mapping version, and operation match the delivery operation;
4. the authorization is approved and not expired, cancelled, revoked, superseded for the intended operation, or otherwise invalidated;
5. current external preconditions required by the destination contract still hold.

A matching digest is necessary but not sufficient: authenticated decision provenance, reviewer authority, tenant mapping, lifecycle state, and current delivery guards remain mandatory.

## Conformance fixtures

The repository must contain language-neutral fixtures with:

- input payload JSON;
- expected canonical UTF-8 bytes;
- expected SHA-256 digest bytes and base64url value;
- positive Python and TypeScript verification;
- negative cases for key order, missing versus null, decimal encoding, negative zero, duplicate keys, Unicode code points, array order, timestamps, changed destination scope, and unknown fields.

The same fixture suite applies to local approval and every external `ApprovalAdapter` implementation.
