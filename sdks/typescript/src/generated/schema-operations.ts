/**
 * @generated
 * Generated from: contracts/openapi/evidentia.openapi.json
 * Regenerate with `make generate-api-contract`.
 */
export const schemaOperationIds = [
  "schemas_create_draft",
  "schemas_get_draft",
  "schemas_get_publication",
  "schemas_list_drafts",
  "schemas_publish_draft",
  "schemas_replace_draft",
] as const;

export type SchemaOperationId = (typeof schemaOperationIds)[number];
