import {
  EvidentiaApiError,
  type ApplySchemaImportResult,
  type SchemaClient,
  type SchemaImportPreview,
  type SchemaImportTarget,
  type SchemaPackage,
} from "@evidentia/typescript-sdk";
import { useMutation } from "@tanstack/react-query";
import { type ChangeEvent, useId, useState } from "react";

import { createSchemaCommandId } from "./contracts";

const MAX_PACKAGE_BYTES = 1_048_576;

function safeEvolutionError(error: unknown): string {
  if (error instanceof EvidentiaApiError) {
    return error.message;
  }
  if (error instanceof Error && error.message.startsWith("Package ")) {
    return error.message;
  }
  return "The schema package operation could not be completed. Check the API and try again.";
}

function isPackage(value: unknown): value is SchemaPackage {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function readPackage(file: File): Promise<SchemaPackage> {
  if (file.size > MAX_PACKAGE_BYTES) {
    throw new Error("Package files must be 1 MiB or smaller.");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(await file.text());
  } catch {
    throw new Error("Package files must contain valid JSON.");
  }
  if (!isPackage(parsed)) {
    throw new Error("Package files must contain one JSON object.");
  }
  return parsed;
}

function savePackage(schemaPackage: SchemaPackage, filename: string) {
  const blob = new Blob([JSON.stringify(schemaPackage, null, 2), "\n"], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function PreviewSummary({
  preview,
}: {
  readonly preview: SchemaImportPreview;
}) {
  return (
    <div className="import-preview" aria-live="polite">
      <div className="import-preview-heading">
        <div>
          <p className="panel-kicker">Validated package</p>
          <h3>
            {preview.creates_new_draft
              ? "Ready to create a new draft"
              : `${preview.compatibility?.level.replaceAll("_", " ") ?? "No changes"}`}
          </h3>
        </div>
        <span className="badge">{preview.kind}</span>
      </div>
      <dl className="schema-card-meta import-metadata">
        <div>
          <dt>Source version</dt>
          <dd>{preview.source_schema_version}</dd>
        </div>
        <div>
          <dt>Package digest</dt>
          <dd title={preview.canonical_sha256}>
            {preview.canonical_sha256.slice(0, 12)}…
          </dd>
        </div>
      </dl>
      {preview.compatibility === null ? (
        <p>
          A new server-owned schema identity will be allocated. No compatibility
          claim is needed because this package has no existing consumers here.
        </p>
      ) : preview.compatibility.changes.length === 0 ? (
        <p>The package content matches the current draft.</p>
      ) : (
        <ul className="change-list">
          {preview.compatibility.changes.map((change) => (
            <li key={`${change.path ?? "schema"}-${change.code}`}>
              <strong>{change.path ?? "Schema"}</strong>: {change.message}
              <span className={`change-level change-level-${change.level}`}>
                {change.level.replaceAll("_", " ")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Accessible package preview/apply controls for a new or existing draft.
 * @skyhook-implements REQ-003
 * @skyhook-implements REQ-016
 * @skyhook-implements NFR-005
 * @skyhook-story STORY-018
 */
export function SchemaImportPanel({
  schemas,
  target,
  onApplied,
}: {
  readonly schemas: SchemaClient;
  readonly target?: SchemaImportTarget;
  readonly onApplied: (result: ApplySchemaImportResult) => void;
}) {
  const inputId = useId();
  const [schemaPackage, setSchemaPackage] = useState<SchemaPackage | null>(
    null,
  );
  const [fileError, setFileError] = useState<string | null>(null);
  const preview = useMutation({
    mutationFn: (candidate: SchemaPackage) =>
      schemas.previewImport(
        candidate,
        target === undefined ? undefined : { schemaId: target.schemaId },
      ),
  });
  const apply = useMutation({
    mutationFn: (candidate: SchemaPackage) =>
      schemas.applyImport(candidate, target, {
        idempotencyKey: createSchemaCommandId(),
      }),
    onSuccess: onApplied,
  });

  async function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    preview.reset();
    apply.reset();
    setSchemaPackage(null);
    setFileError(null);
    if (file === null || file === undefined) {
      return;
    }
    try {
      setSchemaPackage(await readPackage(file));
    } catch (error) {
      setFileError(safeEvolutionError(error));
    }
  }

  return (
    <section
      className="schema-evolution-panel"
      aria-labelledby={`${inputId}-title`}
    >
      <div>
        <p className="panel-kicker">Portable package</p>
        <h2 id={`${inputId}-title`}>
          {target === undefined ? "Import a schema" : "Compare and import"}
        </h2>
        <p>
          Validate and preview canonical JSON before making any change. Package
          identity is provenance, never authority.
        </p>
      </div>
      <div className="package-input-row">
        <div>
          <label htmlFor={`${inputId}-file`}>Schema package</label>
          <input
            accept="application/json,.json"
            id={`${inputId}-file`}
            onChange={(event) => void selectFile(event)}
            type="file"
          />
        </div>
        <button
          className="button button-quiet"
          disabled={schemaPackage === null || preview.isPending}
          onClick={() =>
            schemaPackage !== null && preview.mutate(schemaPackage)
          }
          type="button"
        >
          {preview.isPending ? "Validating…" : "Preview changes"}
        </button>
      </div>
      {fileError === null ? null : (
        <p className="error-banner" role="alert">
          {fileError}
        </p>
      )}
      {preview.error === null ? null : (
        <p className="error-banner" role="alert">
          {safeEvolutionError(preview.error)}
        </p>
      )}
      {preview.data === undefined ? null : (
        <>
          <PreviewSummary preview={preview.data} />
          <button
            className="button button-primary"
            disabled={apply.isPending}
            onClick={() =>
              schemaPackage !== null && apply.mutate(schemaPackage)
            }
            type="button"
          >
            {apply.isPending
              ? "Applying…"
              : target === undefined
                ? "Create draft from package"
                : "Apply to this draft"}
          </button>
        </>
      )}
      {apply.error === null ? null : (
        <p className="error-banner" role="alert">
          {safeEvolutionError(apply.error)}
        </p>
      )}
    </section>
  );
}

/** Export a tenant-authorized draft through the supported SDK operation.
 * @skyhook-implements REQ-003
 * @skyhook-story STORY-018
 */
export function SchemaExportButton({
  kind = "draft",
  schemas,
  schemaId,
  version,
}: {
  readonly kind?: "draft" | "publication";
  readonly schemas: SchemaClient;
  readonly schemaId: string;
  readonly version: number;
}) {
  const exportPackage = useMutation({
    mutationFn: () =>
      kind === "draft"
        ? schemas.exportDraftPackage(schemaId)
        : schemas.exportPublicationPackage(schemaId, version),
    onSuccess: (schemaPackage) =>
      savePackage(
        schemaPackage,
        `evidentia-schema-${schemaId}-${kind}-v${version}.json`,
      ),
  });
  return (
    <div className="export-action">
      <button
        className="button button-quiet"
        disabled={exportPackage.isPending}
        onClick={() => exportPackage.mutate()}
        type="button"
      >
        {exportPackage.isPending
          ? "Exporting…"
          : kind === "draft"
            ? "Export draft JSON"
            : `Export published v${version}`}
      </button>
      {exportPackage.error === null ? null : (
        <span className="inline-error" role="alert">
          {safeEvolutionError(exportPackage.error)}
        </span>
      )}
    </div>
  );
}
