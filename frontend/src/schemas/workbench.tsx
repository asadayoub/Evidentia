import {
  EvidentiaApiError,
  type CurrentContext,
  type SchemaClient,
} from "@evidentia/typescript-sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type ChangeEvent,
  type FormEvent,
  useId,
  useRef,
  useState,
} from "react";
import { Link, useNavigate, useOutletContext, useParams } from "react-router";

import { hasCapability } from "../auth";
import {
  createSchemaCommandId,
  schemaDraftQueryOptions,
  schemaDraftsQueryOptions,
  schemaQueryKeys,
} from "./contracts";
import {
  createWorkbenchField,
  FIELD_TYPE_DESCRIPTORS,
  parseWorkbenchDraft,
  toSchemaDraftContent,
  validateWorkbenchDraft,
  type SchemaFieldKind,
  type WorkbenchDraft,
  type WorkbenchFieldDefinition,
  type WorkbenchValueDefinition,
} from "./model";

const DIRECT_FIELD_TYPES = FIELD_TYPE_DESCRIPTORS.filter(
  (item) => item.creation === "direct",
);

function publicSchemaError(error: unknown): string {
  if (error instanceof EvidentiaApiError) {
    return error.message;
  }
  if (error instanceof Error && error.message.startsWith("schema ")) {
    return "The stored schema could not be opened safely. Ask an administrator to inspect it.";
  }
  return "Evidentia could not reach the schema service. Check the API and try again.";
}

function SchemaStatus({
  title,
  message,
  action,
}: {
  readonly title: string;
  readonly message: string;
  readonly action?: () => void;
}) {
  return (
    <section aria-labelledby="schema-status-title" className="workbench-status">
      <p className="eyebrow">Schema Workbench</p>
      <h1 id="schema-status-title">{title}</h1>
      <p>{message}</p>
      {action === undefined ? null : (
        <button
          className="button button-primary"
          onClick={action}
          type="button"
        >
          Try again
        </button>
      )}
    </section>
  );
}

/** Tenant-scoped schema collection, creation, and empty/error experience.
 * @skyhook-implements REQ-003
 * @skyhook-implements NFR-002
 * @skyhook-implements NFR-005
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export function SchemaWorkbenchPage({
  schemas,
}: {
  readonly schemas: SchemaClient;
}) {
  const context = useOutletContext<CurrentContext>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const drafts = useQuery(schemaDraftsQueryOptions(schemas));
  const canWrite = hasCapability(context, "schemas.write");
  const createDraft = useMutation({
    mutationFn: () =>
      schemas.createDraft(
        { artifacts: [], fields: [], modules: [], releaseLabel: null },
        { idempotencyKey: createSchemaCommandId() },
      ),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({
        queryKey: schemaQueryKeys.drafts(),
      });
      void navigate(`/app/schemas/${created.schema_id}`);
    },
  });

  if (drafts.isPending) {
    return (
      <SchemaStatus
        title="Loading schemas"
        message="Loading the drafts available in this tenant."
      />
    );
  }
  if (drafts.error !== null) {
    const forbidden =
      drafts.error instanceof EvidentiaApiError && drafts.error.status === 403;
    return (
      <SchemaStatus
        title={forbidden ? "Schema access unavailable" : "Schemas unavailable"}
        message={publicSchemaError(drafts.error)}
        {...(forbidden ? {} : { action: () => void drafts.refetch() })}
      />
    );
  }

  return (
    <div className="content-stack workbench-page">
      <header className="page-header workbench-page-header">
        <div>
          <p className="eyebrow">Governed structures</p>
          <h1>Schemas</h1>
          <p>
            Define document-specific fields without changing Evidentia’s core
            data model. Every publication remains immutable and attributable.
          </p>
        </div>
        {canWrite ? (
          <button
            className="button button-primary"
            disabled={createDraft.isPending}
            onClick={() => createDraft.mutate()}
            type="button"
          >
            {createDraft.isPending ? "Creating…" : "Create schema"}
          </button>
        ) : null}
      </header>

      {createDraft.error === null ? null : (
        <p className="error-banner" role="alert">
          {publicSchemaError(createDraft.error)}
        </p>
      )}

      {drafts.data.items.length === 0 ? (
        <section
          className="empty-state schema-empty-state"
          aria-labelledby="empty-title"
        >
          <p className="panel-kicker">No drafts</p>
          <h2 id="empty-title">Start with the structure your documents need</h2>
          <p>
            Add identifiers, dates, amounts, groups, lists, and line-item
            tables. Fields remain governed by this schema instead of becoming
            static application columns.
          </p>
          {canWrite ? (
            <button
              className="button button-primary"
              disabled={createDraft.isPending}
              onClick={() => createDraft.mutate()}
              type="button"
            >
              Create your first schema
            </button>
          ) : (
            <p>
              You have read access. Ask an administrator for schema editing
              permission.
            </p>
          )}
        </section>
      ) : (
        <section aria-labelledby="drafts-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Working copies</p>
              <h2 id="drafts-title">Schema drafts</h2>
            </div>
            <span className="badge">{drafts.data.items.length} available</span>
          </div>
          <div className="schema-card-grid">
            {drafts.data.items.map((draft) => {
              let parsed: WorkbenchDraft;
              try {
                parsed = parseWorkbenchDraft(draft);
              } catch {
                return (
                  <article
                    className="schema-card schema-card-error"
                    key={draft.schema_id}
                  >
                    <p className="panel-kicker">Needs inspection</p>
                    <h3>Unreadable schema draft</h3>
                    <p>
                      The dynamic definition did not pass browser boundary
                      validation.
                    </p>
                  </article>
                );
              }
              return (
                <article className="schema-card" key={draft.schema_id}>
                  <div>
                    <p className="panel-kicker">
                      Draft · revision {parsed.revision}
                    </p>
                    <h3>{parsed.releaseLabel ?? "Untitled schema"}</h3>
                    <p>
                      {parsed.fields.length} root{" "}
                      {parsed.fields.length === 1 ? "field" : "fields"}
                      {parsed.modules.length > 0
                        ? ` · ${parsed.modules.length} modules`
                        : ""}
                    </p>
                  </div>
                  <dl className="schema-card-meta">
                    <div>
                      <dt>Next version</dt>
                      <dd>{parsed.version}</dd>
                    </div>
                    <div>
                      <dt>Updated</dt>
                      <dd>{new Date(parsed.updatedAt).toLocaleString()}</dd>
                    </div>
                  </dl>
                  <Link
                    className="button button-quiet"
                    to={`/app/schemas/${parsed.schemaId}`}
                  >
                    Open draft
                  </Link>
                </article>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}

function replaceAt<T>(
  items: readonly T[],
  index: number,
  value: T,
): readonly T[] {
  return items.map((item, itemIndex) => (itemIndex === index ? value : item));
}

function FieldCollection({
  fields,
  label,
  onChange,
}: {
  readonly fields: readonly WorkbenchFieldDefinition[];
  readonly label: string;
  readonly onChange: (fields: readonly WorkbenchFieldDefinition[]) => void;
}) {
  const [newKey, setNewKey] = useState("");
  const [newKind, setNewKind] = useState<SchemaFieldKind>("string");
  const id = useId();

  function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onChange([...fields, createWorkbenchField(newKind, newKey || "new_field")]);
    setNewKey("");
  }

  return (
    <div className="field-collection">
      {fields.length === 0 ? (
        <p className="field-empty">No {label.toLowerCase()} defined yet.</p>
      ) : (
        fields.map((field, index) => (
          <FieldEditor
            field={field}
            index={index}
            key={`${index}-${field.key}`}
            onChange={(changed) => onChange(replaceAt(fields, index, changed))}
            onRemove={() =>
              onChange(fields.filter((_, itemIndex) => itemIndex !== index))
            }
          />
        ))
      )}
      <form className="add-field-form" onSubmit={add}>
        <div>
          <label htmlFor={`${id}-key`}>New field key</label>
          <input
            id={`${id}-key`}
            onChange={(event) => setNewKey(event.target.value)}
            placeholder="invoice_number"
            required
            value={newKey}
          />
        </div>
        <div>
          <label htmlFor={`${id}-type`}>Field type</label>
          <select
            id={`${id}-type`}
            onChange={(event) =>
              setNewKind(event.target.value as SchemaFieldKind)
            }
            value={newKind}
          >
            {DIRECT_FIELD_TYPES.map((item) => (
              <option key={item.kind} value={item.kind}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <button className="button button-quiet" type="submit">
          Add field
        </button>
      </form>
    </div>
  );
}

function FieldEditor({
  field,
  index,
  onChange,
  onRemove,
}: {
  readonly field: WorkbenchFieldDefinition;
  readonly index: number;
  readonly onChange: (field: WorkbenchFieldDefinition) => void;
  readonly onRemove: () => void;
}) {
  const id = useId();
  const descriptor = FIELD_TYPE_DESCRIPTORS.find(
    (item) => item.kind === field.value.type.kind,
  );

  function changeKind(event: ChangeEvent<HTMLSelectElement>) {
    const replacement = createWorkbenchField(
      event.target.value as SchemaFieldKind,
      field.key,
    );
    onChange({
      ...replacement,
      minimum: field.minimum,
      maximum: field.maximum,
      artifacts: field.artifacts,
    });
  }

  function changeValue(value: WorkbenchValueDefinition) {
    onChange({ ...field, value });
  }

  return (
    <fieldset className="field-editor">
      <legend>Field {index + 1}</legend>
      <div className="field-editor-grid">
        <div>
          <label htmlFor={`${id}-key`}>Machine key</label>
          <input
            id={`${id}-key`}
            onChange={(event) =>
              onChange({ ...field, key: event.target.value })
            }
            value={field.key}
          />
        </div>
        <div>
          <label htmlFor={`${id}-type`}>Value type</label>
          <select
            id={`${id}-type`}
            onChange={changeKind}
            value={field.value.type.kind}
          >
            {FIELD_TYPE_DESCRIPTORS.map((item) => (
              <option
                disabled={
                  item.creation !== "direct" &&
                  item.kind !== field.value.type.kind
                }
                key={item.kind}
                value={item.kind}
              >
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <label className="check-control">
          <input
            checked={field.minimum > 0}
            onChange={(event) =>
              onChange({
                ...field,
                minimum: event.target.checked ? 1 : 0,
                maximum:
                  field.maximum === null
                    ? null
                    : Math.max(event.target.checked ? 1 : 0, field.maximum),
              })
            }
            type="checkbox"
          />
          Required
        </label>
        <label className="check-control">
          <input
            checked={field.maximum === null}
            onChange={(event) =>
              onChange({ ...field, maximum: event.target.checked ? null : 1 })
            }
            type="checkbox"
          />
          Repeatable
        </label>
      </div>
      <p className="field-description">{descriptor?.description}</p>

      {descriptor?.children === "objectFields" ? (
        <section
          className="nested-fields"
          aria-labelledby={`${id}-nested-title`}
        >
          <h4 id={`${id}-nested-title`}>Group fields</h4>
          <FieldCollection
            fields={field.value.objectFields}
            label="Group fields"
            onChange={(objectFields) =>
              changeValue({ ...field.value, objectFields })
            }
          />
        </section>
      ) : null}
      {descriptor?.children === "tableColumns" ? (
        <section
          className="nested-fields"
          aria-labelledby={`${id}-columns-title`}
        >
          <h4 id={`${id}-columns-title`}>Table columns</h4>
          <FieldCollection
            fields={field.value.tableColumns}
            label="Table columns"
            onChange={(tableColumns) =>
              changeValue({ ...field.value, tableColumns })
            }
          />
        </section>
      ) : null}
      {descriptor?.children === "arrayItem" &&
      field.value.arrayItem !== null ? (
        <div className="array-item-summary">
          <span>List item type</span>
          <strong>
            {FIELD_TYPE_DESCRIPTORS.find(
              (item) => item.kind === field.value.arrayItem?.type.kind,
            )?.label ?? field.value.arrayItem.type.kind}
          </strong>
        </div>
      ) : null}

      <button
        className="text-button danger-text"
        onClick={onRemove}
        type="button"
      >
        Remove field
      </button>
    </fieldset>
  );
}

/** Focused draft editor with explicit save, publish, conflict, and recovery states.
 * @skyhook-implements REQ-003
 * @skyhook-implements NFR-001
 * @skyhook-implements NFR-002
 * @skyhook-implements NFR-005
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export function SchemaDraftEditorPage({
  schemas,
}: {
  readonly schemas: SchemaClient;
}) {
  const { schemaId = "" } = useParams();
  const draftQuery = useQuery(schemaDraftQueryOptions(schemas, schemaId));

  if (draftQuery.isPending) {
    if (draftQuery.error === null) {
      return (
        <SchemaStatus
          title="Opening draft"
          message="Loading its latest revision."
        />
      );
    }
  }
  if (draftQuery.error !== null) {
    const notFound =
      draftQuery.error instanceof EvidentiaApiError &&
      draftQuery.error.status === 404;
    return (
      <SchemaStatus
        title={notFound ? "Schema not found" : "Draft unavailable"}
        message={publicSchemaError(draftQuery.error)}
        {...(notFound ? {} : { action: () => void draftQuery.refetch() })}
      />
    );
  }
  if (draftQuery.data === undefined) {
    return (
      <SchemaStatus
        title="Draft unavailable"
        message="The draft could not be opened."
      />
    );
  }

  const initialDraft = parseWorkbenchDraft(draftQuery.data);
  return (
    <SchemaDraftEditor
      initialDraft={initialDraft}
      key={`${initialDraft.schemaId}:${initialDraft.revision}`}
      schemas={schemas}
    />
  );
}

function SchemaDraftEditor({
  initialDraft,
  schemas,
}: {
  readonly initialDraft: WorkbenchDraft;
  readonly schemas: SchemaClient;
}) {
  const context = useOutletContext<CurrentContext>();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(initialDraft);
  const [dirty, setDirty] = useState(false);
  const [publicationReview, setPublicationReview] = useState(false);
  const [acknowledgement, setAcknowledgement] = useState("");
  const notificationRef = useRef<HTMLDivElement>(null);
  const canWrite = hasCapability(context, "schemas.write");
  const canPublish = hasCapability(context, "schemas.publish");
  const save = useMutation({
    mutationFn: (current: WorkbenchDraft) =>
      schemas.replaceDraft(
        current.schemaId,
        toSchemaDraftContent(current),
        current.revision,
        { idempotencyKey: createSchemaCommandId() },
      ),
    onSuccess: async (stored) => {
      setDraft(parseWorkbenchDraft(stored));
      setDirty(false);
      await queryClient.invalidateQueries({
        queryKey: schemaQueryKeys.drafts(),
      });
      notificationRef.current?.focus();
    },
  });
  const publish = useMutation({
    mutationFn: (current: WorkbenchDraft) =>
      schemas.publishDraft(current.schemaId, current.revision, {
        idempotencyKey: createSchemaCommandId(),
        ...(acknowledgement.trim() === ""
          ? {}
          : { acknowledgement: acknowledgement.trim() }),
      }),
    onSuccess: async (result) => {
      setDraft(parseWorkbenchDraft(result.next_draft));
      setDirty(false);
      setPublicationReview(false);
      setAcknowledgement("");
      await queryClient.invalidateQueries({ queryKey: schemaQueryKeys.all });
      notificationRef.current?.focus();
    },
  });

  const issues = validateWorkbenchDraft(draft);
  const publicationIssues = validateWorkbenchDraft(draft, { publishing: true });
  const conflict =
    (save.error instanceof EvidentiaApiError &&
      save.error.code === "schema_revision_conflict") ||
    (publish.error instanceof EvidentiaApiError &&
      publish.error.code === "schema_revision_conflict");

  function updateDraft(changed: WorkbenchDraft) {
    setDraft(changed);
    setDirty(true);
    save.reset();
    publish.reset();
  }

  return (
    <div className="content-stack workbench-editor">
      <div className="editor-breadcrumbs">
        <Link to="/app/schemas">Schemas</Link>
        <span aria-hidden="true">/</span>
        <span>{draft.releaseLabel ?? "Untitled schema"}</span>
      </div>
      <header className="editor-header">
        <div>
          <p className="eyebrow">Draft · next version {draft.version}</p>
          <h1>{draft.releaseLabel ?? "Untitled schema"}</h1>
          <p>
            Revision {draft.revision} · Last updated by {draft.updatedBy}
          </p>
        </div>
        <div className="editor-actions">
          <span
            className={dirty ? "save-state save-state-dirty" : "save-state"}
          >
            {dirty ? "Unsaved changes" : "Saved"}
          </span>
          {canWrite ? (
            <button
              className="button button-quiet"
              disabled={!dirty || issues.length > 0 || save.isPending}
              onClick={() => save.mutate(draft)}
              type="button"
            >
              {save.isPending ? "Saving…" : "Save draft"}
            </button>
          ) : null}
          {canPublish ? (
            <button
              className="button button-primary"
              disabled={
                dirty || publicationIssues.length > 0 || publish.isPending
              }
              onClick={() => setPublicationReview(true)}
              type="button"
            >
              Publish version {draft.version}
            </button>
          ) : null}
        </div>
      </header>

      <div
        aria-live="polite"
        className="sr-notification"
        ref={notificationRef}
        tabIndex={-1}
      >
        {save.isSuccess ? `Draft saved as revision ${draft.revision}.` : null}
        {publish.isSuccess
          ? `Version ${publish.data.publication.version} published. Draft advanced to version ${draft.version}.`
          : null}
      </div>

      {conflict ? (
        <section
          className="conflict-banner"
          aria-labelledby="conflict-title"
          role="alert"
        >
          <div>
            <h2 id="conflict-title">This draft changed elsewhere</h2>
            <p>
              Your edits were not overwritten. Reload the current server
              revision, then apply your changes again.
            </p>
          </div>
          <button
            className="button button-quiet"
            onClick={() => {
              void schemas.getDraft(draft.schemaId).then((current) => {
                queryClient.setQueryData(
                  schemaQueryKeys.draft(draft.schemaId),
                  current,
                );
                setDraft(parseWorkbenchDraft(current));
                setDirty(false);
                save.reset();
                publish.reset();
              });
            }}
            type="button"
          >
            Reload current draft
          </button>
        </section>
      ) : null}
      {!conflict && save.error !== null ? (
        <p className="error-banner" role="alert">
          {publicSchemaError(save.error)} Your local edits are still here.
        </p>
      ) : null}
      {!conflict && publish.error !== null ? (
        <p className="error-banner" role="alert">
          {publicSchemaError(publish.error)} Review compatibility and add an
          acknowledgement when required.
        </p>
      ) : null}

      {issues.length > 0 ? (
        <section
          className="validation-summary"
          aria-labelledby="validation-title"
        >
          <h2 id="validation-title">Resolve before saving</h2>
          <ul>
            {issues.map((issue) => (
              <li key={`${issue.path}-${issue.message}`}>{issue.message}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="editor-panel" aria-labelledby="identity-title">
        <div className="editor-panel-heading">
          <div>
            <p className="panel-kicker">Identity</p>
            <h2 id="identity-title">Schema details</h2>
          </div>
          <span className="badge">{draft.schemaId.slice(0, 8)}</span>
        </div>
        <label htmlFor="schema-release-label">Release label</label>
        <input
          disabled={!canWrite}
          id="schema-release-label"
          maxLength={64}
          onChange={(event) =>
            updateDraft({ ...draft, releaseLabel: event.target.value || null })
          }
          placeholder="Invoice intake"
          value={draft.releaseLabel ?? ""}
        />
        <p className="field-help">
          A human-readable label. Stable machine identity remains server-owned.
        </p>
      </section>

      <section className="editor-panel" aria-labelledby="fields-title">
        <div className="editor-panel-heading">
          <div>
            <p className="panel-kicker">Dynamic definition</p>
            <h2 id="fields-title">Fields</h2>
          </div>
          <span className="badge">{draft.fields.length} root fields</span>
        </div>
        {canWrite ? (
          <FieldCollection
            fields={draft.fields}
            label="Fields"
            onChange={(fields) => updateDraft({ ...draft, fields })}
          />
        ) : (
          <div className="read-only-fields">
            {draft.fields.map((field) => (
              <div className="read-only-field" key={field.key}>
                <strong>{field.key}</strong>
                <span>{field.value.type.kind}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {publicationReview ? (
        <section
          aria-labelledby="publication-review-title"
          className="publication-review"
        >
          <div>
            <p className="panel-kicker">Immutable action</p>
            <h2 id="publication-review-title">
              Publish version {draft.version}?
            </h2>
            <p>
              Publication freezes the current content and advances this working
              draft. It cannot rewrite an earlier version.
            </p>
          </div>
          <label htmlFor="publication-acknowledgement">
            Change acknowledgement{" "}
            <span className="optional-label">Optional</span>
          </label>
          <textarea
            id="publication-acknowledgement"
            maxLength={2000}
            onChange={(event) => setAcknowledgement(event.target.value)}
            placeholder="Explain reviewed behavior-changing or breaking effects when required."
            rows={3}
            value={acknowledgement}
          />
          <div className="publication-actions">
            <button
              className="button button-quiet"
              onClick={() => setPublicationReview(false)}
              type="button"
            >
              Continue editing
            </button>
            <button
              className="button button-primary"
              disabled={publish.isPending}
              onClick={() => publish.mutate(draft)}
              type="button"
            >
              {publish.isPending
                ? "Publishing…"
                : `Confirm version ${draft.version}`}
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
