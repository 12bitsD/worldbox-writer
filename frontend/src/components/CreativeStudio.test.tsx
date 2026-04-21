import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SimulationState } from "../types";
import { CreativeStudio } from "./CreativeStudio";

const saveWiki = vi.fn();
const getDiagnostics = vi.fn();

vi.mock("../utils/api", () => ({
  saveWiki: (...args: unknown[]) => saveWiki(...args),
  getDiagnostics: (...args: unknown[]) => getDiagnostics(...args),
  updateRenderedText: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

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
    features: { branching_enabled: true, dual_loop_enabled: true },
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

  it("renders dual-loop diagnostics summary", async () => {
    getDiagnostics.mockResolvedValue({
      sim_id: "sim-test",
      status: "complete",
      active_branch_id: "main",
      routing: {},
      memory: {
        total_entries: 2,
        active_entries: 1,
        archived_entries: 1,
        summary_entries: 1,
        event_entries: 1,
        latest_tick: 1,
        vector_backend: "simple",
        vector_backend_requested: "auto",
        vector_backend_fallback_reason: null,
      },
      llm: {
        total_calls: 1,
        total_duration_ms: 180,
        estimated_prompt_tokens: 120,
        estimated_completion_tokens: 200,
        estimated_cost_usd: 0.0012,
        routes: [],
      },
      dual_loop: {
        enabled: true,
        contract_version: "dual-loop-v1",
        adapter_mode: "legacy-compatibility-v1",
        scene_plan: {
          scene_id: "scene-1",
          branch_id: "main",
          tick: 1,
          title: "第一幕",
          objective: "测试目标",
          setting: "地点：王城",
          public_summary: "王城的局势正在升温",
          spotlight_character_ids: ["char-1"],
          narrative_pressure: "balanced",
          constraints: [],
          source_node_id: "node-1",
          metadata: {},
        },
        action_intents: [],
        intent_critiques: [
          {
            critique_id: "critique-1",
            scene_id: "scene-1",
            intent_id: "intent-1",
            actor_id: "char-1",
            actor_name: "角色A",
            accepted: false,
            reason_code: "world_rule_violation",
            severity: "blocking",
            reason: "违反世界规则",
            revision_hint: "改写行动",
            metadata: {},
          },
        ],
        scene_script: {
          script_id: "script-1",
          scene_id: "scene-1",
          branch_id: "main",
          tick: 1,
          title: "第一幕",
          summary: "王城的局势正在升温",
          public_facts: ["王城的局势正在升温"],
          participating_character_ids: ["char-1"],
          accepted_intent_ids: [],
          rejected_intent_ids: [],
          beats: [],
          source_node_id: "node-1",
          metadata: {},
        },
        prompt_traces: [],
      },
    });

    render(
      <CreativeStudio simId="sim-test" state={buildState()} onRefresh={vi.fn()} />
    );

    fireEvent.click(screen.getByRole("button", { name: "诊断" }));

    expect(await screen.findByText("dual-loop-v1")).toBeInTheDocument();
    expect(await screen.findByText("legacy-compatibility-v1")).toBeInTheDocument();
    expect(await screen.findByText("王城的局势正在升温")).toBeInTheDocument();
    expect(await screen.findByText(/world_rule_violation/)).toBeInTheDocument();
  });
});
