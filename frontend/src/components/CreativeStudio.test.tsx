import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SimulationState } from "../types";
import { CreativeStudio } from "./CreativeStudio";

const saveWiki = vi.fn();
const getDiagnostics = vi.fn();

vi.mock("../utils/api", () => ({
  saveWiki: (...args: unknown[]) => saveWiki(...args),
  getDiagnostics: (...args: unknown[]) => getDiagnostics(...args),
  updateRenderedText: vi.fn(),
}));

function buildState(): SimulationState {
  return {
    sim_id: "sim-test",
    status: "complete",
    premise: "测试前提",
    world: {
      title: "旧标题",
      premise: "测试前提",
      tick: 1,
      is_complete: true,
      characters: [
        {
          id: "char-1",
          name: "角色A",
          description: "",
          personality: "沉着",
          goals: ["守住王城"],
          status: "alive",
          memory: [],
          relationships: {},
        },
      ],
      factions: [],
      locations: [],
      world_rules: ["规则一"],
      constraints: [],
      branches: {
        main: {
          label: "Main Timeline",
          forked_from_node: null,
        },
      },
      active_branch_id: "main",
    },
    nodes: [],
    telemetry: [],
    intervention_context: null,
    error: null,
    features: { branching_enabled: true },
  };
}

describe("CreativeStudio", () => {
  it("submits the current wiki form", async () => {
    saveWiki.mockResolvedValue({
      message: "Wiki 已保存",
      issues: [],
      world: buildState().world,
    });

    render(
      <CreativeStudio simId="sim-test" state={buildState()} onRefresh={vi.fn()} />
    );

    fireEvent.change(screen.getByDisplayValue("旧标题"), {
      target: { value: "新标题" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存 Wiki" }));

    await waitFor(() =>
      expect(saveWiki).toHaveBeenCalledWith(
        "sim-test",
        expect.objectContaining({ title: "新标题" })
      )
    );
    expect(await screen.findByText("Wiki 已保存")).toBeInTheDocument();
  });
});
