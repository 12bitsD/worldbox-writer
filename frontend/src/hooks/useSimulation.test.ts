import { describe, expect, it } from "vitest";

import { isStreamingStatus } from "./simulationTransport";
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

describe("isStreamingStatus", () => {
  it("matches statuses that should keep transport attached", () => {
    expect(isStreamingStatus("initializing")).toBe(true);
    expect(isStreamingStatus("running")).toBe(true);
    expect(isStreamingStatus("waiting")).toBe(true);
  });

  it("excludes terminal statuses", () => {
    expect(isStreamingStatus("complete")).toBe(false);
    expect(isStreamingStatus("error")).toBe(false);
  });
});
