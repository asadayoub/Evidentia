import {
  type ApplySchemaImportResult,
  EvidentiaApiError,
  type AccessClient,
  type CurrentContext,
  type PublishSchemaResult,
  type SchemaClient,
  type SchemaDraft,
  type SchemaImportPreview,
} from "@evidentia/typescript-sdk";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { SCHEMA_WORKBENCH_JOURNEY } from "../test/schema-workbench-fixtures";

const {
  context: CONTEXT,
  emptyDraft: EMPTY_DRAFT,
  session: SESSION,
} = SCHEMA_WORKBENCH_JOURNEY;

function accessClient(context: CurrentContext = CONTEXT): AccessClient {
  return {
    getCurrentContext: () => Promise.resolve(context),
    getSession: () => Promise.resolve(SESSION),
    login: () => Promise.resolve(SESSION),
    logout: () => Promise.resolve(),
    selectTenant: () => Promise.resolve(SESSION),
  };
}

function schemaClient(overrides: Partial<SchemaClient> = {}): SchemaClient {
  return {
    applyImport: () => Promise.reject(new Error("not used")),
    createDraft: () => Promise.resolve(EMPTY_DRAFT),
    exportDraftPackage: () => Promise.reject(new Error("not used")),
    exportPublicationPackage: () => Promise.reject(new Error("not used")),
    getDraft: () => Promise.resolve(EMPTY_DRAFT),
    getPublication: () => Promise.reject(new Error("not used")),
    listDrafts: () => Promise.resolve({ items: [], next_cursor: null }),
    publishDraft: () => Promise.reject(new Error("not used")),
    previewImport: () => Promise.reject(new Error("not used")),
    replaceDraft: () => Promise.reject(new Error("not used")),
    ...overrides,
  };
}

function storedDraft(
  content: Parameters<SchemaClient["replaceDraft"]>[1],
  revision: number,
): SchemaDraft {
  return {
    ...EMPTY_DRAFT,
    content,
    revision,
    updated_at: `2026-10-08T06:0${revision}:00Z`,
  };
}

describe("Schema Workbench", () => {
  it("renders an accessible empty state and creates a server-identified draft", async () => {
    const createDraft = vi.fn<SchemaClient["createDraft"]>(() =>
      Promise.resolve(EMPTY_DRAFT),
    );
    const schemas = schemaClient({ createDraft });
    const { container } = render(
      <App
        access={accessClient()}
        schemas={schemas}
        initialEntries={["/app/schemas"]}
      />,
    );

    expect(
      await screen.findByRole("heading", {
        name: "Start with the structure your documents need",
      }),
    ).toBeInTheDocument();
    expect((await axe.run(container)).violations).toEqual([]);

    fireEvent.click(
      screen.getByRole("button", { name: "Create your first schema" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Untitled schema" }),
    ).toBeInTheDocument();
    expect(createDraft).toHaveBeenCalledOnce();
    expect(createDraft.mock.calls[0]?.[0]).toEqual({
      artifacts: [],
      fields: [],
      modules: [],
      releaseLabel: null,
    });
    expect(createDraft.mock.calls[0]?.[1]?.idempotencyKey).toMatch(
      /^[0-9a-f-]{36}$/u,
    );
  });

  it("edits, saves, confirms, and publishes a dynamic schema", async () => {
    const replaceDraft = vi.fn<SchemaClient["replaceDraft"]>(
      (_schemaId, content) => Promise.resolve(storedDraft(content, 2)),
    );
    const publishDraft = vi.fn<SchemaClient["publishDraft"]>(
      (_schemaId, revision) => {
        const nextDraft = storedDraft(
          {
            artifacts: [],
            fields: [
              {
                key: "invoice_number",
                cardinality: { minimum: 1, maximum: 1 },
                artifacts: [],
                value: {
                  type: {
                    kind: "string",
                    min_length: 0,
                    max_length: null,
                    pattern: null,
                  },
                  artifacts: [],
                },
              },
            ],
            modules: [],
            releaseLabel: "Invoice intake",
          },
          revision + 1,
        );
        const result: PublishSchemaResult = {
          publication: {
            acknowledgement: null,
            actor_id: "operator-1",
            content_sha256: "a".repeat(64),
            correlation_id: "publish-request",
            previous_version: null,
            published_at: "2026-10-08T06:10:00Z",
            schema_id: EMPTY_DRAFT.schema_id,
            snapshot: {},
            version: 1,
          },
          next_draft: { ...nextDraft, version: 2 },
        };
        return Promise.resolve(result);
      },
    );
    const schemas = schemaClient({ publishDraft, replaceDraft });
    const { container } = render(
      <App
        access={accessClient()}
        schemas={schemas}
        initialEntries={[`/app/schemas/${EMPTY_DRAFT.schema_id}`]}
      />,
    );

    fireEvent.change(await screen.findByLabelText("Release label"), {
      target: { value: "Invoice intake" },
    });
    fireEvent.change(screen.getByLabelText("New field key"), {
      target: { value: "invoice_number" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add field" }));
    fireEvent.click(screen.getByLabelText("Required"));
    expect((await axe.run(container)).violations).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(replaceDraft).toHaveBeenCalledOnce());
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Publish version 1" }));
    expect(
      screen.getByRole("heading", { name: "Publish version 1?" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm version 1" }));

    await waitFor(() => expect(publishDraft).toHaveBeenCalledOnce());
    expect(await screen.findByText(/Version 1 published/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Publish version 2" }),
    ).toBeInTheDocument();
  });

  it("preserves local edits and offers reload after a revision conflict", async () => {
    const currentDraft = { ...EMPTY_DRAFT, revision: 2 };
    const getDraft = vi
      .fn<SchemaClient["getDraft"]>()
      .mockResolvedValueOnce(EMPTY_DRAFT)
      .mockRejectedValueOnce(new TypeError("private network detail"))
      .mockResolvedValue(currentDraft);
    const replaceDraft = vi.fn<SchemaClient["replaceDraft"]>(() =>
      Promise.reject(
        new EvidentiaApiError(
          409,
          "schema_revision_conflict",
          "The schema draft has changed.",
        ),
      ),
    );
    render(
      <App
        access={accessClient()}
        schemas={schemaClient({ getDraft, replaceDraft })}
        initialEntries={[`/app/schemas/${EMPTY_DRAFT.schema_id}`]}
      />,
    );

    fireEvent.change(await screen.findByLabelText("New field key"), {
      target: { value: "local_change" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add field" }));
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    expect(
      await screen.findByRole("heading", {
        name: "This draft changed elsewhere",
      }),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("local_change")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reload current draft" }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Reload current draft" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your local edits are still here; try reloading again.",
    );
    expect(screen.queryByText(/private network detail/u)).toBeNull();
    expect(screen.getByDisplayValue("local_change")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Reload current draft" }),
    );
    await waitFor(() => expect(getDraft).toHaveBeenCalledTimes(3));
    expect(await screen.findByText(/Revision 2/)).toBeInTheDocument();
    expect(screen.queryByDisplayValue("local_change")).toBeNull();
  });

  it("keeps invalid drafts local and disables persistence", async () => {
    render(
      <App
        access={accessClient()}
        schemas={schemaClient()}
        initialEntries={[`/app/schemas/${EMPTY_DRAFT.schema_id}`]}
      />,
    );

    fireEvent.change(await screen.findByLabelText("New field key"), {
      target: { value: "Invalid key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add field" }));

    expect(
      screen.getByRole("heading", { name: "Resolve before saving" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Publish version 1" }),
    ).toBeDisabled();
  });

  it("recovers the list after a safe transient failure", async () => {
    const listDrafts = vi
      .fn<SchemaClient["listDrafts"]>()
      .mockRejectedValueOnce(new TypeError("network detail must not leak"))
      .mockResolvedValue({ items: [], next_cursor: null });
    render(
      <App
        access={accessClient()}
        schemas={schemaClient({ listDrafts })}
        initialEntries={["/app/schemas"]}
      />,
    );

    expect(
      await screen.findByRole("heading", { name: "Schemas unavailable" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/network detail/u)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(
      await screen.findByRole("heading", {
        name: "Start with the structure your documents need",
      }),
    ).toBeInTheDocument();
    expect(listDrafts).toHaveBeenCalledTimes(2);
  });

  it("previews a portable package before creating a server-owned draft", async () => {
    const previewResult: SchemaImportPreview = {
      canonical_sha256: "a".repeat(64),
      compatibility: null,
      content: {
        artifacts: [],
        fields: [],
        modules: [
          {
            artifacts: [],
            fields: [],
            id: "20000000-0000-4000-8000-000000000001",
            key: "supplier",
            releaseLabel: "Synthetic supplier module",
            version: 1,
          },
        ],
      },
      creates_new_draft: true,
      envelope_version: 1,
      format: "evidentia.schema-draft",
      kind: "draft",
      source_schema_id: EMPTY_DRAFT.schema_id,
      source_schema_version: 1,
      target_revision: null,
      target_schema_id: null,
    };
    const appliedResult: ApplySchemaImportResult = {
      created: true,
      draft: EMPTY_DRAFT,
      package_sha256: "a".repeat(64),
    };
    const previewImport = vi
      .fn<SchemaClient["previewImport"]>()
      .mockResolvedValue(previewResult);
    const applyImport = vi
      .fn<SchemaClient["applyImport"]>()
      .mockResolvedValue(appliedResult);
    render(
      <App
        access={accessClient()}
        schemas={schemaClient({ applyImport, previewImport })}
        initialEntries={["/app/schemas"]}
      />,
    );
    await screen.findByRole("heading", {
      name: "Start with the structure your documents need",
    });
    const schemaPackage = SCHEMA_WORKBENCH_JOURNEY.composedPackage;
    fireEvent.change(screen.getByLabelText("Schema package"), {
      target: {
        files: [
          new File([JSON.stringify(schemaPackage)], "schema.json", {
            type: "application/json",
          }),
        ],
      },
    });

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Preview changes" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));
    expect(
      await screen.findByRole("heading", {
        name: "Ready to create a new draft",
      }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Create draft from package" }),
    );

    await waitFor(() => expect(applyImport).toHaveBeenCalledOnce());
    expect(previewImport).toHaveBeenCalledWith(schemaPackage, undefined);
    expect(applyImport.mock.calls[0]?.[1]).toBeUndefined();
    expect(applyImport.mock.calls[0]?.[2].idempotencyKey).toMatch(
      /^[0-9a-f-]{36}$/u,
    );
  });

  it("shows existing-target compatibility and preserves state on import conflict", async () => {
    const previewImport = vi
      .fn<SchemaClient["previewImport"]>()
      .mockResolvedValue({
        canonical_sha256: "b".repeat(64),
        compatibility: {
          changes: [
            {
              code: "required_field_added",
              level: "breaking",
              message: "required field added",
              path: "approval_code",
            },
          ],
          level: "breaking",
          requires_acknowledgement: true,
        },
        content: { artifacts: [], fields: [], modules: [] },
        creates_new_draft: false,
        envelope_version: 1,
        format: "evidentia.schema-draft",
        kind: "draft",
        source_schema_id: "223e4567-e89b-12d3-a456-426614174000",
        source_schema_version: 2,
        target_revision: 1,
        target_schema_id: EMPTY_DRAFT.schema_id,
      });
    const applyImport = vi.fn<SchemaClient["applyImport"]>(() =>
      Promise.reject(
        new EvidentiaApiError(
          409,
          "schema_revision_conflict",
          "The schema draft has changed.",
        ),
      ),
    );
    render(
      <App
        access={accessClient()}
        schemas={schemaClient({ applyImport, previewImport })}
        initialEntries={[`/app/schemas/${EMPTY_DRAFT.schema_id}`]}
      />,
    );
    await screen.findByRole("heading", { name: "Untitled schema" });
    const schemaPackage = {
      format: "evidentia.schema-draft",
      version: 1,
      schema: {
        artifacts: [],
        fields: [],
        id: "223e4567-e89b-12d3-a456-426614174000",
        modules: [],
        releaseLabel: "Imported",
        version: 2,
      },
    };
    fireEvent.change(screen.getByLabelText("Schema package"), {
      target: {
        files: [
          new File([JSON.stringify(schemaPackage)], "schema.json", {
            type: "application/json",
          }),
        ],
      },
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Preview changes" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));

    expect(
      await screen.findByRole("heading", { name: "breaking" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/approval_code/u)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Apply to this draft" }),
    );

    expect(
      await screen.findByText("The schema draft has changed."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Untitled schema" }),
    ).toBeInTheDocument();
  });

  it("rejects malformed package files before calling the API", async () => {
    const previewImport = vi.fn<SchemaClient["previewImport"]>();
    render(
      <App
        access={accessClient()}
        schemas={schemaClient({ previewImport })}
        initialEntries={["/app/schemas"]}
      />,
    );
    await screen.findByRole("heading", { name: "Import a schema" });
    fireEvent.change(screen.getByLabelText("Schema package"), {
      target: {
        files: [
          new File(["not-json"], "schema.json", { type: "application/json" }),
        ],
      },
    });

    expect(
      await screen.findByText("Package files must contain valid JSON."),
    ).toBeInTheDocument();
    expect(previewImport).not.toHaveBeenCalled();
  });

  it("renders forbidden and read-only states from trusted authority", async () => {
    const forbidden = schemaClient({
      listDrafts: () =>
        Promise.reject(
          new EvidentiaApiError(
            403,
            "access_denied",
            "The request is not authorized.",
          ),
        ),
    });
    const first = render(
      <App
        access={accessClient()}
        schemas={forbidden}
        initialEntries={["/app/schemas"]}
      />,
    );
    expect(
      await screen.findByRole("heading", { name: "Schema access unavailable" }),
    ).toBeInTheDocument();
    first.unmount();

    render(
      <App
        access={accessClient({ ...CONTEXT, capabilities: ["schemas.read"] })}
        schemas={schemaClient({
          listDrafts: () =>
            Promise.resolve({ items: [EMPTY_DRAFT], next_cursor: null }),
        })}
        initialEntries={["/app/schemas"]}
      />,
    );
    expect(
      await screen.findByRole("link", { name: "Open draft" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create schema" })).toBeNull();
  });
});
