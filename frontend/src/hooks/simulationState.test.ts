import { describe, expect, it } from "vitest";

import type { SimulationState, StoryNode, TelemetryEvent } from "../types";
import {
  appendStreamingToken,
  mergeSimulationSnapshot,
  mergeTelemetryEvents,
  upsertNode,
} from "./simulationState";

function buildNode(overrides: Partial<StoryNode> = {}): StoryNode {
  return {
    id: "node-1",
    title: "第一幕",
    description: "事件",
    node_type: "development",
    rendered_text: null,
    tick: 1,
    requires_intervention: false,
    branch_id: "main",
    merged_from_ids: [],
    ...overrides,
  };
}

function buildTelemetry(overrides: Partial<TelemetryEvent> = {}): TelemetryEvent {
  return {
    event_id: "evt-1",
    sim_id: "sim-1",
    trace_id: "trace-1",
    request_id: null,
    parent_event_id: null,
    tick: 1,
    agent: "actor",
    stage: "proposal_generated",
    level: "info",
    span_kind: "event",
    message: "事件",
    payload: {},
    provider: null,
    model: null,
    duration_ms: null,
    ts: "2026-01-01T00:00:01+00:00",
    ...overrides,
  };
}

function buildState(overrides: Partial<SimulationState> = {}): SimulationState {
  return {
    sim_id: "sim-1",
    status: "running",
    premise: "测试前提",
    world: null,
    nodes: [],
    telemetry: [],
    intervention_context: null,
    error: null,
    ...overrides,
  };
}

describe("simulationState helpers", () => {
  it("upsertNode merges final rendered node into an existing streaming placeholder", () => {
    const placeholder = buildNode({ streaming_text: "正在渲染" });
    const finalNode = buildNode({ rendered_text: "最终正文" });

    const merged = upsertNode([placeholder], finalNode);

    expect(merged).toHaveLength(1);
    expect(merged[0].rendered_text).toBe("最终正文");
    expect(merged[0].streaming_text).toBeUndefined();
  });

  it("appendStreamingToken targets the explicitly provided node id", () => {
    const first = buildNode({ id: "node-1" });
    const second = buildNode({ id: "node-2" });

    const updated = appendStreamingToken([first, second], "片段", "node-1");

    expect(updated[0].streaming_text).toBe("片段");
    expect(updated[1].streaming_text).toBeUndefined();
  });

  it("mergeTelemetryEvents deduplicates by event id", () => {
    const current = [buildTelemetry({ event_id: "evt-1", message: "旧消息" })];
    const incoming = [buildTelemetry({ event_id: "evt-1", message: "新消息" })];

    const merged = mergeTelemetryEvents(current, incoming);

    expect(merged).toHaveLength(1);
    expect(merged[0].message).toBe("新消息");
  });

  it("mergeSimulationSnapshot keeps existing nodes while merging refreshed state", () => {
    const current = buildState({
      nodes: [buildNode({ id: "node-1", streaming_text: "正在渲染" })],
      telemetry: [buildTelemetry({ event_id: "evt-1" })],
    });
    const incoming = buildState({
      status: "complete",
      nodes: [buildNode({ id: "node-1", rendered_text: "最终正文" })],
      telemetry: [buildTelemetry({ event_id: "evt-2", tick: 2 })],
    });

    const merged = mergeSimulationSnapshot(current, incoming);

    expect(merged.status).toBe("complete");
    expect(merged.nodes).toHaveLength(1);
    expect(merged.nodes[0].rendered_text).toBe("最终正文");
    expect(merged.telemetry).toHaveLength(2);
  });
});
