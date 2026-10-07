/**
 * @generated
 * Generated from: contracts/openapi/evidentia.openapi.json
 * Regenerate with `make generate-api-contract`.
 */
export const accessOperationIds = [
  "access_get_current_context",
  "access_login_local",
  "access_logout",
  "access_select_tenant",
] as const;

export type AccessOperationId = (typeof accessOperationIds)[number];
