/**
 * Return the supported TypeScript SDK package version.
 *
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-007
 */
export function sdkVersion(): string {
  return "0.1.0";
}

export {
  accessOperationIds,
  type AccessOperationId,
} from "./generated/access-operations.js";

export {
  schemaOperationIds,
  type SchemaOperationId,
} from "./generated/schema-operations.js";

export {
  createAccessClient,
  createEvidentiaClient,
  createSchemaClient,
  EvidentiaApiError,
  type ApplySchemaImportResult,
  type AccessClient,
  type AccessRequestOptions,
  type CookieReader,
  type CurrentContext,
  type EvidentiaClient,
  type EvidentiaClientOptions,
  type LoginRequest,
  type SessionResponse,
  type PublishSchemaResult,
  type SchemaClient,
  type SchemaDraft,
  type SchemaDraftContent,
  type SchemaDraftListOptions,
  type SchemaDraftPage,
  type SchemaImportPreview,
  type SchemaImportTarget,
  type SchemaMutationOptions,
  type SchemaPublication,
  type SchemaPackage,
  type SchemaRequestOptions,
  type TenantSummary,
} from "./client.js";

export type {
  components as EvidentiaComponents,
  operations as EvidentiaOperations,
  paths as EvidentiaPaths,
} from "./generated/evidentia.js";
