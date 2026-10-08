import {
  createAccessClient,
  createEvidentiaClient,
  createSchemaClient,
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
const browserClient = createEvidentiaClient({ baseUrl: apiBaseUrl() });

export const browserAccessClient = createAccessClient(browserClient);

/** Shared schema lifecycle client over the same credentialed browser transport.
 * @skyhook-implements REQ-003
 * @skyhook-implements REQ-012
 * @skyhook-story H98W5WTJBWT8EY0Q10P3KPCEEB
 */
export const browserSchemaClient = createSchemaClient(browserClient);
