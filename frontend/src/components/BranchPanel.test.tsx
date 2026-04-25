import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { BranchPanel } from "./BranchPanel";
import type { BranchCompareSummary, WorldData } from "../types";

afterEach(() => cleanup());

const world: WorldData = {
  title: "测试世界",
  premise: "测试前提",
  tick: 4,
  is_complete: false,
  characters: [],
  factions: [],
  locations: [],
  world_rules: [],
  constraints: [],
  branches: {
    main: { label: "主线", forked_from_node: null, pacing: "balanced" },
    branch_a: {
      label: "支线A",
      forked_from_node: "node-2",
      source_branch_id: "main",
      created_at_tick: 2,
      latest_tick: 4,
      nodes_count: 4,
      pacing: "intense",
    },
  },
  active_branch_id: "main",
};

const compare: Record<string, BranchCompareSummary> = {
  main: {
    branch_id: "main",
    label: "主线",
    forked_from_node: null,
    source_branch_id: null,
    source_sim_id: null,
    created_at_tick: 0,
    latest_node_id: "node-4",
    latest_tick: 4,
    nodes_count: 4,
    last_node_summary: "主线摘要",
    status: "complete",
    pacing: "balanced",
    is_active: true,
  },
  branch_a: {
    branch_id: "branch_a",
    label: "支线A",
    forked_from_node: "node-2",
    source_branch_id: "main",
    source_sim_id: "sim-1",
    created_at_tick: 2,
    latest_node_id: "branch-node-4",
    latest_tick: 4,
    nodes_count: 4,
    last_node_summary: "支线摘要",
    status: "waiting",
    pacing: "intense",
    is_active: false,
  },
};

describe("BranchPanel", () => {
  it("renders branch compare information", () => {
    render(
      <BranchPanel
        world={world}
        compare={compare}
        isRunning={false}
        onSwitch={() => undefined}
        onPacingChange={() => undefined}
      />
    );

    expect(screen.getByText("时间线 (Timelines)")).toBeInTheDocument();
    expect(screen.getByText("主线")).toBeInTheDocument();
    expect(screen.getByText("支线A")).toBeInTheDocument();
  });

  it("invokes switch callback on click", () => {
    const onSwitch = vi.fn();

    render(
      <BranchPanel
        world={world}
        compare={compare}
        isRunning={false}
        onSwitch={onSwitch}
        onPacingChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText("支线A"));

    expect(onSwitch).toHaveBeenCalledWith("branch_a");
  });
});
