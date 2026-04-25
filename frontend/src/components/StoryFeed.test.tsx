import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StoryNode, TelemetryEvent, WorldData } from "../types";
import { StoryFeed } from "./StoryFeed";

afterEach(() => cleanup());

function buildNode(overrides: Partial<StoryNode> = {}): StoryNode {
  return {
    id: "node-1",
    title: "第一幕",
    description: "阿璃来到断桥。",
    node_type: "development",
    rendered_text: "阿璃在潮雾中停步。",
    tick: 1,
    requires_intervention: false,
    parent_ids: [],
    branch_id: "main",
    merged_from_ids: [],
    ...overrides,
  };
}

function buildWorld(): WorldData {
  return {
    title: "测试世界",
    premise: "测试前提",
    tick: 1,
    is_complete: false,
    characters: [
      {
        id: "char-1",
        name: "阿璃",
        description: "潮雾中的旅人",
        personality: "谨慎",
        goals: ["查明断桥真相"],
        status: "alive",
        memory: ["见过潮雾"],
        relationships: {},
      },
    ],
    factions: [],
    locations: [],
    world_rules: [],
    constraints: [],
    branches: { main: { label: "主线", forked_from_node: null } },
    active_branch_id: "main",
  };
}

function buildEvent(overrides: Partial<TelemetryEvent> = {}): TelemetryEvent {
  return {
    event_id: "evt-1",
    sim_id: "sim-1",
    trace_id: "trace-1",
    request_id: null,
    parent_event_id: null,
    tick: 1,
    agent: "gate_keeper",
    stage: "gate_check",
    level: "error",
    span_kind: "system",
    message: "失败！李四没有带刀",
    payload: {},
    provider: null,
    model: null,
    duration_ms: 12,
    branch_id: "main",
    forked_from_node_id: null,
    source_branch_id: null,
    source_sim_id: null,
    ts: "2026-01-01T00:00:00+00:00",
    ...overrides,
  };
}

describe("StoryFeed", () => {
  it("separates inner-loop console from novel reading", () => {
    render(
      <StoryFeed
        nodes={[buildNode()]}
        isRunning={false}
        branchingEnabled={false}
        activeBranchId="main"
        onForkNode={vi.fn()}
      />
    );

    expect(screen.getAllByText("故事正文 (Manuscript)")[0]).toBeInTheDocument();
    
    // Toggle the simulation log
    fireEvent.click(screen.getByRole("button", { name: "显示推演日志" }));

    expect(screen.getByText("推演日志 (Sim Log)")).toBeInTheDocument();
    expect(screen.getByText("内循环")).toBeInTheDocument();
    expect(screen.getByText("阿璃来到断桥。")).toBeInTheDocument();
    expect(screen.getByText("阿璃在潮雾中停步。")).toBeInTheDocument();
  });

  it("surfaces SceneScript lineage for rendered nodes", () => {
    render(
      <StoryFeed
        nodes={[
          buildNode({
            scene_script_summary: "GM 结算后的场景摘要。",
            narrator_input_source: "scene_script",
          }),
        ]}
        isRunning={false}
        branchingEnabled={false}
        activeBranchId="main"
        onForkNode={vi.fn()}
      />
    );

    // Toggle the simulation log
    fireEvent.click(screen.getByRole("button", { name: "显示推演日志" }));

    expect(screen.getByText("SceneScript")).toBeInTheDocument();
    expect(screen.getByText("GM 结算后的场景摘要。")).toBeInTheDocument();
  });

  it("opens inline entity cards from character mentions", () => {
    render(
      <StoryFeed
        nodes={[buildNode()]}
        isRunning={false}
        branchingEnabled={false}
        activeBranchId="main"
        onForkNode={vi.fn()}
        simId="sim-1"
        world={buildWorld()}
      />
    );

    fireEvent.click(screen.getAllByRole("button", { name: "阿璃" })[0]);

    expect(screen.getByRole("dialog", { name: "阿璃 设定卡" })).toBeInTheDocument();
    expect(screen.getByText("最近记忆：见过潮雾")).toBeInTheDocument();
  });

  it("renders harness telemetry as status chips", () => {
    render(
      <StoryFeed
        nodes={[buildNode()]}
        isRunning
        branchingEnabled={false}
        activeBranchId="main"
        onForkNode={vi.fn()}
        telemetryEvents={[buildEvent()]}
      />
    );

    // Toggle the simulation log
    fireEvent.click(screen.getByRole("button", { name: "显示推演日志" }));

    expect(screen.getByText("工程呼吸灯")).toBeInTheDocument();
    expect(screen.getByText("规则引擎校验：失败！李四没有带刀")).toBeInTheDocument();
  });
});
