import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { TelemetryEvent } from "../types";
import { ProgressPanel } from "./ProgressPanel";

afterEach(() => cleanup());

function buildEvent(partial: Partial<TelemetryEvent>): TelemetryEvent {
  return {
    event_id: partial.event_id ?? "evt-1",
    sim_id: partial.sim_id ?? "sim-1",
    trace_id: partial.trace_id ?? "trace-1",
    request_id: partial.request_id ?? null,
    parent_event_id: partial.parent_event_id ?? null,
    tick: partial.tick ?? 0,
    agent: partial.agent ?? "director",
    stage: partial.stage ?? "world_initialized",
    level: partial.level ?? "info",
    span_kind: partial.span_kind ?? "llm",
    message: partial.message ?? "世界骨架初始化完成",
    payload: partial.payload ?? {},
    provider: partial.provider ?? "openai",
    model: partial.model ?? "gpt-4.1-mini",
    duration_ms: partial.duration_ms ?? 100,
    branch_id: partial.branch_id ?? "main",
    forked_from_node_id: partial.forked_from_node_id ?? null,
    source_branch_id: partial.source_branch_id ?? null,
    source_sim_id: partial.source_sim_id ?? null,
    ts: partial.ts ?? "2026-01-01T00:00:00+00:00",
  };
}

describe("ProgressPanel", () => {
  it("renders latest stage progress in the main panel", () => {
    render(
      <ProgressPanel
        isRunning
        events={[
          buildEvent({
            event_id: "evt-1",
            agent: "director",
            stage: "world_initialized",
            message: "世界骨架初始化完成",
          }),
          buildEvent({
            event_id: "evt-2",
            agent: "actor",
            stage: "proposal_generated",
            message: "生成了新的候选事件",
            tick: 1,
          }),
        ]}
      />
    );

    expect(screen.getByText("首次推演进度")).toBeInTheDocument();
    expect(screen.getByText("生成了新的候选事件")).toBeInTheDocument();
    expect(screen.getByText("生成第一幕")).toBeInTheDocument();
  });

  it("shows narration as active when narrator has started streaming", () => {
    render(
      <ProgressPanel
        isRunning
        events={[
          buildEvent({
            event_id: "evt-1",
            agent: "director",
            stage: "world_initialized",
            message: "世界骨架初始化完成",
          }),
          buildEvent({
            event_id: "evt-2",
            agent: "node_detector",
            stage: "node_committed",
            message: "新故事节点已固化",
            tick: 1,
          }),
          buildEvent({
            event_id: "evt-3",
            agent: "narrator",
            stage: "started",
            message: "开始渲染小说文本",
            tick: 1,
            duration_ms: null,
          }),
        ]}
      />
    );

    expect(screen.getByText("正在出字")).toBeInTheDocument();
    expect(screen.getByText("开始渲染小说文本")).toBeInTheDocument();
  });
});
