import { describe, expect, it } from "vitest";

import { sdkVersion } from "../src/index";

describe("TypeScript SDK boundary", () => {
  it("exposes its supported version", () => {
    expect(sdkVersion()).toBe("0.1.0");
  });
});
