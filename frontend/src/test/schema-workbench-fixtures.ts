import type {
  CurrentContext,
  SchemaDraft,
  SessionResponse,
} from "@evidentia/typescript-sdk";

export interface SchemaWorkbenchJourneyFixture {
  readonly session: SessionResponse;
  readonly context: CurrentContext;
  readonly emptyDraft: SchemaDraft;
  readonly composedPackage: Record<string, unknown>;
}

/** Deterministic browser identities and dynamic content for the complete schema journey.
 * The matching JSON fixture is synthetic and exercised against disposable PostgreSQL.
 * @skyhook-implements REQ-003
 * @skyhook-implements REQ-016
 * @skyhook-implements REQ-017
 * @skyhook-story 265YM4FNANJAH2J338BKAWFXDM
 */
export const SCHEMA_WORKBENCH_JOURNEY: SchemaWorkbenchJourneyFixture = {
  session: {
    active_tenant_id: "tenant-1",
    available_tenants: [],
    operator_id: "operator-1",
    tenant_selection_required: false,
  },
  context: {
    authenticated_at: "2026-10-08T06:00:00Z",
    capabilities: ["schemas.publish", "schemas.read", "schemas.write"],
    correlation_id: "request-1",
    display_name: "Schema Administrator",
    login_identifier: "schema-journey-owner@example.test",
    membership_id: "membership-1",
    operator_id: "operator-1",
    session_id: "session-1",
    tenant_id: "tenant-1",
    tenant_name: "Schema Journey",
    tenant_slug: "schema-journey",
  },
  emptyDraft: {
    schema_id: "123e4567-e89b-12d3-a456-426614174000",
    version: 1,
    revision: 1,
    content: { artifacts: [], fields: [], modules: [], releaseLabel: null },
    created_by: "operator-1",
    updated_by: "operator-1",
    created_at: "2026-10-08T06:00:00Z",
    updated_at: "2026-10-08T06:00:00Z",
  },
  composedPackage: {
    format: "evidentia.schema-draft",
    version: 1,
    schema: {
      artifacts: [],
      fields: [],
      id: "10000000-0000-4000-8000-000000000001",
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
      releaseLabel: "Synthetic composed invoice",
      version: 1,
    },
  },
};
