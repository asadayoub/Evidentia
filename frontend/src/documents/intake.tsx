import {
  EvidentiaApiError,
  type CurrentContext,
  type DocumentClient,
  type DocumentCustody,
} from "@evidentia/typescript-sdk";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useOutletContext } from "react-router";

import { hasCapability } from "../auth";

function uploadError(error: unknown): string {
  if (error instanceof EvidentiaApiError) {
    if (error.status === 413) {
      return "This file is larger than the configured upload limit. Choose a smaller file.";
    }
    if (error.status === 415) {
      return "This file type is not supported. Choose a PDF, Word document, or scanned image.";
    }
    if (error.status === 403) {
      return "Your workspace membership does not allow document uploads.";
    }
    if (error.status === 503) {
      return "The document could not be stored. Check local artifact storage and try again.";
    }
    return error.message;
  }
  return "Evidentia could not reach the document service. Check the API and try again.";
}

function CustodyReceipt({ document }: { readonly document: DocumentCustody }) {
  return (
    <section aria-labelledby="document-receipt-title" className="feature-panel">
      <div>
        <p className="panel-kicker">Original source preserved</p>
        <h2 id="document-receipt-title">{document.original_filename}</h2>
      </div>
      <dl className="document-receipt-meta">
        <div>
          <dt>Status</dt>
          <dd>{document.status}</dd>
        </div>
        <div>
          <dt>Size</dt>
          <dd>{new Intl.NumberFormat().format(document.byte_size)} bytes</dd>
        </div>
        <div>
          <dt>SHA-256</dt>
          <dd className="document-digest">{document.content_sha256 ?? "Pending"}</dd>
        </div>
        <div>
          <dt>Document ID</dt>
          <dd className="document-digest">{document.document_id}</dd>
        </div>
      </dl>
      <p className="muted-copy">
        The original is stored as an opaque source. Text extraction and OCR are
        not run during upload.
      </p>
    </section>
  );
}

/** Authenticated browser upload and original-custody receipt experience.
 * @skyhook-implements REQ-001
 * @skyhook-implements NFR-002
 * @skyhook-implements NFR-005
 * @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
 */
export function DocumentIntakePage({
  documents,
}: {
  readonly documents: DocumentClient;
}) {
  const context = useOutletContext<CurrentContext>();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [custody, setCustody] = useState<DocumentCustody | null>(null);
  const canWrite = hasCapability(context, "documents.write");
  const upload = useMutation({
    mutationFn: async () => {
      if (selectedFile === null) {
        throw new Error("Choose a document before uploading.");
      }
      const idempotencyKey = globalThis.crypto.randomUUID();
      return documents.uploadOriginal(selectedFile, idempotencyKey);
    },
    onSuccess: (result) => setCustody(result),
  });

  return (
    <div className="content-stack document-intake">
      <header className="page-header">
        <p className="eyebrow">Document intake</p>
        <h1>Preserve an original</h1>
        <p>
          Upload a source document to establish its tenant scoped custody record,
          integrity digest, and traceable receipt.
        </p>
      </header>

      <section aria-labelledby="document-upload-title" className="feature-panel document-upload-panel">
        <div>
          <p className="panel-kicker">Original source</p>
          <h2 id="document-upload-title">Choose a document to preserve</h2>
          <p className="muted-copy">
            Supported formats: PDF, DOCX, JPEG, PNG, and TIFF. Maximum size is
            configured by the deployment.
          </p>
        </div>
        {!canWrite ? (
          <p className="muted-copy" role="status">
            You have read access to document custody, but your workspace role does not allow uploads.
          </p>
        ) : null}
        {canWrite ? (
          <>
        <label className="document-file-field" htmlFor="original-document">
          <span>Document file</span>
          <input
            accept="application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/jpeg,image/png,image/tiff"
            id="original-document"
            onChange={(event) => {
              setSelectedFile(event.currentTarget.files?.[0] ?? null);
              upload.reset();
            }}
            type="file"
          />
        </label>
        {selectedFile === null ? null : (
          <p aria-live="polite" className="muted-copy">
            Selected: {selectedFile.name} · {new Intl.NumberFormat().format(selectedFile.size)} bytes
          </p>
        )}
        {upload.error === null ? null : (
          <p className="error-banner" role="alert">{uploadError(upload.error)}</p>
        )}
        {upload.isSuccess ? (
          <p className="success-banner" role="status">
            Original preserved successfully. Its receipt is shown below.
          </p>
        ) : null}
        <button
          className="button button-primary document-upload-button"
          disabled={selectedFile === null || upload.isPending}
          onClick={() => upload.mutate()}
          type="button"
        >
          {upload.isPending ? "Preserving original…" : "Preserve original"}
        </button>
          </>
        ) : null}
      </section>

      {custody === null ? null : <CustodyReceipt document={custody} />}
    </div>
  );
}
