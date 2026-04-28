import { describe, expect, it } from "vitest";

import { shouldAutoRestoreSession } from "./useSimulation";

describe("shouldAutoRestoreSession", () => {
  it("does not auto-open failed or still-initializing sessions after refresh", () => {
    expect(shouldAutoRestoreSession("error")).toBe(false);
    expect(shouldAutoRestoreSession("initializing")).toBe(false);
  });

  it("auto-opens sessions that can still be meaningfully resumed", () => {
    expect(shouldAutoRestoreSession("running")).toBe(true);
    expect(shouldAutoRestoreSession("waiting")).toBe(true);
    expect(shouldAutoRestoreSession("complete")).toBe(true);
  });
});
