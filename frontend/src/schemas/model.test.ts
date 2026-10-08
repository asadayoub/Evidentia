import type { SchemaDraft } from "@evidentia/typescript-sdk";
import { describe, expect, it } from "vitest";

import {
  createWorkbenchField,
  FIELD_TYPE_DESCRIPTORS,
  parseWorkbenchDraft,
  toSchemaDraftContent,
  validateWorkbenchDraft,
  type WorkbenchDraft,
} from "./model";

const STORED_DRAFT: SchemaDraft = {
  schema_id: "123e4567-e89b-12d3-a456-426614174000",
  version: 1,
  revision: 4,
  content: {
    releaseLabel: "invoice-v1",
    artifacts: [],
    modules: [],
    fields: [
      {
        key: "supplier",
        cardinality: { minimum: 1, maximum: 1 },
        artifacts: [],
        value: {
          type: { kind: "object", min_properties: 1, max_properties: null },
          artifacts: [],
          objectFields: [
            {
              key: "name",
              cardinality: { minimum: 1, maximum: 1 },
              artifacts: [],
              value: {
                type: {
                  kind: "string",
                  min_length: 1,
                  max_length: 200,
                  pattern: null,
                },
                artifacts: [],
              },
            },
          ],
        },
      },
    ],
  },
  created_by: "operator-1",
  updated_by: "operator-2",
  created_at: "2026-10-08T06:00:00Z",
  updated_at: "2026-10-08T06:10:00Z",
};

describe("Schema Workbench contracts", () => {
  it("round-trips recursive dynamic content without adding authority fields", () => {
    const parsed = parseWorkbenchDraft(STORED_DRAFT);

    expect(parsed.fields[0]?.value.objectFields[0]?.key).toBe("name");
    expect(toSchemaDraftContent(parsed)).toEqual(STORED_DRAFT.content);
    expect(toSchemaDraftContent(parsed)).not.toHaveProperty("schema_id");
    expect(toSchemaDraftContent(parsed)).not.toHaveProperty("revision");
  });

  it("rejects malformed transport content before it enters editor state", () => {
    expect(() =>
      parseWorkbenchDraft({
        ...STORED_DRAFT,
        content: {
          fields: [{ key: "unsafe", value: { type: { kind: "future" } } }],
        },
      }),
    ).toThrow("cardinality must be an object");
  });

  it("defines every core type in one extensible registry", () => {
    expect(FIELD_TYPE_DESCRIPTORS.map((item) => item.kind)).toEqual([
      "string",
      "identifier",
      "integer",
      "decimal",
      "money",
      "boolean",
      "date",
      "datetime",
      "enum",
      "object",
      "array",
      "table",
      "reference",
      "artifact_reference",
      "extension",
    ]);
    expect(createWorkbenchField("table").value.tableColumns).toEqual([]);
    expect(createWorkbenchField("array").value.arrayItem?.type.kind).toBe(
      "string",
    );
    expect(() => createWorkbenchField("extension")).toThrow(
      "requires an advanced configuration workflow",
    );
  });

  it("reports path-addressed key, duplicate, cardinality, and publication issues", () => {
    const field = createWorkbenchField("string", "Bad key");
    const duplicate = { ...field, key: "same", minimum: 2, maximum: 1 };
    const draft: WorkbenchDraft = {
      ...parseWorkbenchDraft(STORED_DRAFT),
      fields: [{ ...field, key: "same" }, duplicate],
    };

    expect(validateWorkbenchDraft(draft)).toEqual([
      {
        path: "fields.1.key",
        message: "Field key “same” is already used in this group.",
      },
      {
        path: "fields.1.cardinality",
        message: "Maximum occurrences must be at least the minimum.",
      },
    ]);
    expect(
      validateWorkbenchDraft(
        { ...draft, fields: [], modules: [] },
        { publishing: true },
      ),
    ).toContainEqual({
      path: "fields",
      message: "Add at least one field or module before publishing.",
    });
  });
});
