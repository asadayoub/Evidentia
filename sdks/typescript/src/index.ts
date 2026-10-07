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
