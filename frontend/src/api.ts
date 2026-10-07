import {
  createAccessClient,
  createEvidentiaClient,
} from "@evidentia/typescript-sdk";

const DEFAULT_API_URL = "http://127.0.0.1:8000";

/** Resolve the public API origin used by the browser application.
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-017
 */
export function apiBaseUrl(): string {
  const configured: unknown = import.meta.env["VITE_EVIDENTIA_API_URL"];
  return typeof configured === "string" && configured.length > 0
    ? configured
    : DEFAULT_API_URL;
}

/** Shared access client; all browser API interactions flow through the SDK.
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-017
 */
export const browserAccessClient = createAccessClient(
  createEvidentiaClient({ baseUrl: apiBaseUrl() }),
);
