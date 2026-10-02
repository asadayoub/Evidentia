import { sdkVersion } from "@evidentia/typescript-sdk";

/**
 * Render the bootstrap application shell.
 *
 * @skyhook-implements REQ-012
 * @skyhook-story STORY-007
 */
export function App() {
  return (
    <main className="shell">
      <section aria-labelledby="evidentia-title" className="panel">
        <p className="eyebrow">Governed foundation</p>
        <h1 id="evidentia-title">Evidentia</h1>
        <p>
          The API, worker, web application, and SDK workspaces are ready for
          capability implementation.
        </p>
        <p className="version">TypeScript SDK {sdkVersion()}</p>
      </section>
    </main>
  );
}
