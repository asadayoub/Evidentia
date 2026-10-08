import type {
  SchemaDraft,
  SchemaDraftContent,
} from "@evidentia/typescript-sdk";

/** JSON-safe value retained by the dynamic schema boundary.
 * @skyhook-implements REQ-003
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export type JsonValue =
  | boolean
  | number
  | string
  | null
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };

/** JSON object retained without converting dynamic field configuration to static product fields.
 * @skyhook-implements REQ-003
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export type JsonObject = { readonly [key: string]: JsonValue };

/** Stable core type discriminators supported by the schema domain.
 * @skyhook-implements REQ-003
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export type SchemaFieldKind =
  | "array"
  | "artifact_reference"
  | "boolean"
  | "date"
  | "datetime"
  | "decimal"
  | "enum"
  | "extension"
  | "identifier"
  | "integer"
  | "money"
  | "object"
  | "reference"
  | "string"
  | "table";

export type ChildCollection =
  "arrayItem" | "none" | "objectFields" | "tableColumns";

/** Registry metadata drives controls without hard-coding field behavior into pages.
 * @skyhook-implements REQ-003
 * @skyhook-implements NFR-005
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export interface FieldTypeDescriptor {
  readonly kind: SchemaFieldKind;
  readonly label: string;
  readonly description: string;
  readonly children: ChildCollection;
  readonly creation: "direct" | "requires-advanced-configuration";
  readonly defaultConfiguration: JsonObject;
}

export const FIELD_TYPE_DESCRIPTORS: readonly FieldTypeDescriptor[] = [
  {
    kind: "string",
    label: "Text",
    description: "Unicode text with optional length and pattern rules.",
    children: "none",
    creation: "direct",
    defaultConfiguration: { min_length: 0, max_length: null, pattern: null },
  },
  {
    kind: "identifier",
    label: "Identifier",
    description: "An opaque identifier with explicit format constraints.",
    children: "none",
    creation: "direct",
    defaultConfiguration: { min_length: 1, max_length: 255, pattern: null },
  },
  {
    kind: "integer",
    label: "Integer",
    description: "A whole number with optional inclusive bounds.",
    children: "none",
    creation: "direct",
    defaultConfiguration: { minimum: null, maximum: null },
  },
  {
    kind: "decimal",
    label: "Decimal",
    description: "An exact decimal with optional precision, scale, and bounds.",
    children: "none",
    creation: "direct",
    defaultConfiguration: {
      precision: null,
      scale: null,
      minimum: null,
      maximum: null,
    },
  },
  {
    kind: "money",
    label: "Money",
    description: "An exact decimal amount paired with a currency policy.",
    children: "none",
    creation: "direct",
    defaultConfiguration: {
      amount: {
        kind: "decimal",
        precision: 18,
        scale: 2,
        minimum: null,
        maximum: null,
      },
      allowed_currencies: [],
    },
  },
  {
    kind: "boolean",
    label: "Yes / no",
    description: "A strict boolean value.",
    children: "none",
    creation: "direct",
    defaultConfiguration: {},
  },
  {
    kind: "date",
    label: "Date",
    description: "A calendar date without a time or timezone.",
    children: "none",
    creation: "direct",
    defaultConfiguration: {},
  },
  {
    kind: "datetime",
    label: "Date and time",
    description: "A timezone-aware instant normalized to UTC.",
    children: "none",
    creation: "direct",
    defaultConfiguration: {},
  },
  {
    kind: "enum",
    label: "Choice",
    description: "One value from a governed set of machine keys.",
    children: "none",
    creation: "direct",
    defaultConfiguration: { values: ["option_one"] },
  },
  {
    kind: "object",
    label: "Group",
    description: "A nested group containing its own governed fields.",
    children: "objectFields",
    creation: "direct",
    defaultConfiguration: { min_properties: 0, max_properties: null },
  },
  {
    kind: "array",
    label: "List",
    description: "A repeated value with optional count and uniqueness rules.",
    children: "arrayItem",
    creation: "direct",
    defaultConfiguration: {
      min_items: 0,
      max_items: null,
      unique_items: false,
    },
  },
  {
    kind: "table",
    label: "Line-item table",
    description: "Repeated rows with governed columns.",
    children: "tableColumns",
    creation: "direct",
    defaultConfiguration: { min_rows: 0, max_rows: null },
  },
  {
    kind: "reference",
    label: "Record reference",
    description: "A typed reference to another governed record target.",
    children: "none",
    creation: "requires-advanced-configuration",
    defaultConfiguration: {},
  },
  {
    kind: "artifact_reference",
    label: "Artifact reference",
    description: "A reference to a governed immutable artifact.",
    children: "none",
    creation: "requires-advanced-configuration",
    defaultConfiguration: {},
  },
  {
    kind: "extension",
    label: "Extension type",
    description: "A namespaced, versioned type supplied by an extension.",
    children: "none",
    creation: "requires-advanced-configuration",
    defaultConfiguration: {},
  },
] as const;

const FIELD_KINDS = new Set(FIELD_TYPE_DESCRIPTORS.map((item) => item.kind));
const FIELD_KEY = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;

/** Editable type definition with lossless dynamic configuration.
 * @skyhook-implements REQ-003
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export interface WorkbenchTypeDefinition {
  readonly kind: SchemaFieldKind;
  readonly configuration: JsonObject;
}

/** Recursive editable value definition used by fields, arrays, groups, and tables.
 * @skyhook-implements REQ-003
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export interface WorkbenchValueDefinition {
  readonly type: WorkbenchTypeDefinition;
  readonly artifacts: readonly JsonObject[];
  readonly objectFields: readonly WorkbenchFieldDefinition[];
  readonly arrayItem: WorkbenchValueDefinition | null;
  readonly tableColumns: readonly WorkbenchFieldDefinition[];
}

/** Recursive field definition independent of React and transport frameworks.
 * @skyhook-implements REQ-003
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export interface WorkbenchFieldDefinition {
  readonly key: string;
  readonly minimum: number;
  readonly maximum: number | null;
  readonly artifacts: readonly JsonObject[];
  readonly value: WorkbenchValueDefinition;
}

/** Trusted editor model parsed from the generated SDK's dynamic content boundary.
 * @skyhook-implements REQ-003
 * @skyhook-implements NFR-008
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export interface WorkbenchDraft {
  readonly schemaId: string;
  readonly version: number;
  readonly revision: number;
  readonly releaseLabel: string | null;
  readonly fields: readonly WorkbenchFieldDefinition[];
  readonly modules: readonly JsonObject[];
  readonly artifacts: readonly JsonObject[];
  readonly updatedAt: string;
  readonly updatedBy: string;
}

/** One actionable, path-addressed editor validation issue.
 * @skyhook-implements NFR-005
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export interface WorkbenchIssue {
  readonly path: string;
  readonly message: string;
}

/** Reject malformed dynamic content before it enters editor state.
 * @skyhook-implements REQ-003
 * @skyhook-implements NFR-008
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export function parseWorkbenchDraft(draft: SchemaDraft): WorkbenchDraft {
  const content = objectValue(draft.content, "schema content");
  const fields = arrayValue(content["fields"] ?? [], "schema fields").map(
    (item, index) => parseField(item, `fields.${index}`),
  );
  const releaseLabel = content["releaseLabel"];
  if (
    releaseLabel !== undefined &&
    releaseLabel !== null &&
    typeof releaseLabel !== "string"
  ) {
    throw new Error("schema release label must be a string or null");
  }
  return {
    schemaId: draft.schema_id,
    version: draft.version,
    revision: draft.revision,
    releaseLabel: releaseLabel ?? null,
    fields,
    modules: jsonObjects(content["modules"] ?? [], "schema modules"),
    artifacts: jsonObjects(content["artifacts"] ?? [], "schema artifacts"),
    updatedAt: draft.updated_at,
    updatedBy: draft.updated_by,
  };
}

/** Serialize editor state to the generated SDK command without client authority fields.
 * @skyhook-implements REQ-003
 * @skyhook-implements NFR-008
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export function toSchemaDraftContent(
  draft: WorkbenchDraft,
): SchemaDraftContent {
  return {
    releaseLabel: draft.releaseLabel,
    fields: draft.fields.map(fieldOut),
    modules: draft.modules.map((item) => ({ ...item })),
    artifacts: draft.artifacts.map((item) => ({ ...item })),
  };
}

/** Create a valid directly-configurable field from registry metadata.
 * @skyhook-implements REQ-003
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export function createWorkbenchField(
  kind: SchemaFieldKind,
  key = "new_field",
): WorkbenchFieldDefinition {
  const descriptor = FIELD_TYPE_DESCRIPTORS.find((item) => item.kind === kind);
  if (descriptor === undefined || descriptor.creation !== "direct") {
    throw new Error("field type requires an advanced configuration workflow");
  }
  const value: WorkbenchValueDefinition = {
    type: { kind, configuration: descriptor.defaultConfiguration },
    artifacts: [],
    objectFields: [],
    arrayItem:
      descriptor.children === "arrayItem"
        ? createWorkbenchField("string", "item").value
        : null,
    tableColumns: [],
  };
  return { key, minimum: 0, maximum: 1, artifacts: [], value };
}

/** Validate editor invariants before Save or Publish is enabled.
 * @skyhook-implements REQ-003
 * @skyhook-implements NFR-005
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export function validateWorkbenchDraft(
  draft: WorkbenchDraft,
  options: { readonly publishing?: boolean } = {},
): readonly WorkbenchIssue[] {
  const issues: WorkbenchIssue[] = [];
  if (
    options.publishing === true &&
    draft.fields.length + draft.modules.length === 0
  ) {
    issues.push({
      path: "fields",
      message: "Add at least one field or module before publishing.",
    });
  }
  validateFields(draft.fields, "fields", issues);
  return issues;
}

function validateFields(
  fields: readonly WorkbenchFieldDefinition[],
  path: string,
  issues: WorkbenchIssue[],
): void {
  const keys = new Set<string>();
  fields.forEach((field, index) => {
    const fieldPath = `${path}.${index}`;
    if (!FIELD_KEY.test(field.key)) {
      issues.push({
        path: `${fieldPath}.key`,
        message: "Use a lower_snake_case field key.",
      });
    } else if (keys.has(field.key)) {
      issues.push({
        path: `${fieldPath}.key`,
        message: `Field key “${field.key}” is already used in this group.`,
      });
    }
    keys.add(field.key);
    if (
      field.minimum < 0 ||
      (field.maximum !== null && field.maximum < field.minimum)
    ) {
      issues.push({
        path: `${fieldPath}.cardinality`,
        message: "Maximum occurrences must be at least the minimum.",
      });
    }
    validateFields(
      field.value.objectFields,
      `${fieldPath}.objectFields`,
      issues,
    );
    validateFields(
      field.value.tableColumns,
      `${fieldPath}.tableColumns`,
      issues,
    );
  });
}

function parseField(raw: unknown, path: string): WorkbenchFieldDefinition {
  const field = objectValue(raw, path);
  const key = stringValue(field["key"], `${path}.key`);
  const cardinality = objectValue(field["cardinality"], `${path}.cardinality`);
  const minimum = integerValue(cardinality["minimum"], `${path}.minimum`);
  const maximumRaw = cardinality["maximum"];
  const maximum =
    maximumRaw === null ? null : integerValue(maximumRaw, `${path}.maximum`);
  return {
    key,
    minimum,
    maximum,
    artifacts: jsonObjects(field["artifacts"] ?? [], `${path}.artifacts`),
    value: parseValue(field["value"], `${path}.value`),
  };
}

function parseValue(raw: unknown, path: string): WorkbenchValueDefinition {
  const value = objectValue(raw, path);
  const type = objectValue(value["type"], `${path}.type`);
  const kind = stringValue(type["kind"], `${path}.type.kind`);
  if (!FIELD_KINDS.has(kind as SchemaFieldKind)) {
    throw new Error(`${path}.type.kind is not supported`);
  }
  const configuration = { ...type };
  delete configuration["kind"];
  return {
    type: {
      kind: kind as SchemaFieldKind,
      configuration: jsonObject(configuration, `${path}.type`),
    },
    artifacts: jsonObjects(value["artifacts"] ?? [], `${path}.artifacts`),
    objectFields: arrayValue(
      value["objectFields"] ?? [],
      `${path}.objectFields`,
    ).map((item, index) => parseField(item, `${path}.objectFields.${index}`)),
    arrayItem:
      value["arrayItem"] === undefined
        ? null
        : parseValue(value["arrayItem"], `${path}.arrayItem`),
    tableColumns: arrayValue(
      value["tableColumns"] ?? [],
      `${path}.tableColumns`,
    ).map((item, index) => parseField(item, `${path}.tableColumns.${index}`)),
  };
}

function fieldOut(field: WorkbenchFieldDefinition): Record<string, unknown> {
  const result: Record<string, unknown> = {
    key: field.key,
    cardinality: { minimum: field.minimum, maximum: field.maximum },
    artifacts: field.artifacts.map((item) => ({ ...item })),
    value: valueOut(field.value),
  };
  return result;
}

function valueOut(value: WorkbenchValueDefinition): Record<string, unknown> {
  const result: Record<string, unknown> = {
    type: { kind: value.type.kind, ...value.type.configuration },
    artifacts: value.artifacts.map((item) => ({ ...item })),
  };
  if (value.objectFields.length > 0) {
    result["objectFields"] = value.objectFields.map(fieldOut);
  }
  if (value.arrayItem !== null) {
    result["arrayItem"] = valueOut(value.arrayItem);
  }
  if (value.tableColumns.length > 0) {
    result["tableColumns"] = value.tableColumns.map(fieldOut);
  }
  return result;
}

function objectValue(raw: unknown, subject: string): Record<string, unknown> {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new Error(`${subject} must be an object`);
  }
  return raw as Record<string, unknown>;
}

function arrayValue(raw: unknown, subject: string): readonly unknown[] {
  if (!Array.isArray(raw)) {
    throw new Error(`${subject} must be an array`);
  }
  return raw;
}

function stringValue(raw: unknown, subject: string): string {
  if (typeof raw !== "string") {
    throw new Error(`${subject} must be a string`);
  }
  return raw;
}

function integerValue(raw: unknown, subject: string): number {
  if (!Number.isInteger(raw)) {
    throw new Error(`${subject} must be an integer`);
  }
  return raw as number;
}

function jsonObject(raw: unknown, subject: string): JsonObject {
  const value = objectValue(raw, subject);
  for (const [key, item] of Object.entries(value)) {
    jsonValue(item, `${subject}.${key}`);
  }
  return value as JsonObject;
}

function jsonObjects(raw: unknown, subject: string): readonly JsonObject[] {
  return arrayValue(raw, subject).map((item, index) =>
    jsonObject(item, `${subject}.${index}`),
  );
}

function jsonValue(raw: unknown, subject: string): JsonValue {
  if (
    raw === null ||
    typeof raw === "boolean" ||
    typeof raw === "string" ||
    (typeof raw === "number" && Number.isFinite(raw))
  ) {
    return raw;
  }
  if (Array.isArray(raw)) {
    return raw.map((item, index) => jsonValue(item, `${subject}.${index}`));
  }
  return jsonObject(raw, subject);
}
