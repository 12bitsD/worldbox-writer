import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const mockUseSimulation = vi.hoisted(() => vi.fn());

vi.mock("./hooks/useSimulation", () => ({
  useSimulation: mockUseSimulation,
}));

afterEach(() => {
  cleanup();
  mockUseSimulation.mockReset();
});

function baseSimulationHook() {
  return {
    simId: null,
    state: null,
    branchCompare: null,
    loading: false,
    error: null,
    recentSessions: [],
    start: vi.fn(),
    openSession: vi.fn(),
    sendIntervention: vi.fn(),
    forkAtNode: vi.fn(),
    activateBranch: vi.fn(),
    setBranchPacing: vi.fn(),
    doExport: vi.fn(),
    refresh: vi.fn(),
    reset: vi.fn(),
  };
}

describe("App startup shell", () => {
  it("keeps API errors visible on the start screen", () => {
    mockUseSimulation.mockReturnValue({
      ...baseSimulationHook(),
      error: "Failed to fetch",
    });

    render(<App />);

    expect(screen.getByText("错误：Failed to fetch")).toBeInTheDocument();
    expect(screen.getByText("故事前提")).toBeInTheDocument();
  });
});
