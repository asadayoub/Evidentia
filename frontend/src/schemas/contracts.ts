import type { SchemaClient } from "@evidentia/typescript-sdk";
import { queryOptions } from "@tanstack/react-query";

/** Stable query keys keep tenant-scoped schema cache invalidation explicit.
 * @skyhook-implements REQ-003
 * @skyhook-implements NFR-008
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export const schemaQueryKeys = {
  all: ["schemas"] as const,
  drafts: () => ["schemas", "drafts"] as const,
  draft: (schemaId: string) => ["schemas", "drafts", schemaId] as const,
  publication: (schemaId: string, version: number) =>
    ["schemas", "publications", schemaId, version] as const,
};

/** Query the first deterministic workbench page through the supported SDK.
 * @skyhook-implements REQ-003
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export function schemaDraftsQueryOptions(schema: SchemaClient) {
  return queryOptions({
    queryKey: schemaQueryKeys.drafts(),
    queryFn: ({ signal }) => schema.listDrafts({ limit: 100, signal }),
    retry: false,
  });
}

/** Query one server-authoritative draft by stable schema identity.
 * @skyhook-implements REQ-003
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export function schemaDraftQueryOptions(
  schema: SchemaClient,
  schemaId: string,
) {
  return queryOptions({
    queryKey: schemaQueryKeys.draft(schemaId),
    queryFn: ({ signal }) => schema.getDraft(schemaId, { signal }),
    retry: false,
  });
}

/** Browser-safe command identity generated independently for each user intent.
 * @skyhook-implements NFR-001
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export function createSchemaCommandId(): string {
  if (typeof globalThis.crypto?.randomUUID !== "function") {
    throw new Error("A secure schema command identity is unavailable.");
  }
  return globalThis.crypto.randomUUID();
}
