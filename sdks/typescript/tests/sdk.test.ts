import { describe, expect, it } from "vitest";

import { accessOperationIds, sdkVersion } from "../src/index";

describe("TypeScript SDK boundary", () => {
  it("exposes its supported version", () => {
    expect(sdkVersion()).toBe("0.1.0");
  });

  it("exposes access operations generated from the checked contract", () => {
    expect(accessOperationIds).toEqual([
      "access_get_current_context",
      "access_login_local",
      "access_logout",
      "access_select_tenant",
    ]);
  });
});
