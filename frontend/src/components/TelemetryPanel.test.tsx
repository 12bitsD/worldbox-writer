import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { TelemetryPanel } from "./TelemetryPanel";
import { sprint6TelemetryFixture } from "../test/sprint6-fixtures";

afterEach(() => cleanup());

describe("TelemetryPanel", () => {
  it("renders the empty idle state", () => {
    render(<TelemetryPanel events={[]} isRunning={false} />);

    expect(screen.getByText("Telemetry")).toBeInTheDocument();
    expect(screen.getByText("当前会话还没有遥测事件。")).toBeInTheDocument();
  });

  it("renders the running empty state", () => {
    render(<TelemetryPanel events={[]} isRunning />);

    expect(screen.getByText("等待第一条关键事件...")).toBeInTheDocument();
  });

  it("renders fixture-driven telemetry events in reverse chronological order", () => {
    render(<TelemetryPanel events={sprint6TelemetryFixture} isRunning />);

    expect(screen.getByText("3 / 3 / 3 条事件")).toBeInTheDocument();
    expect(screen.getByText("新故事节点已固化")).toBeInTheDocument();
    expect(screen.getByText("候选事件被边界层拒绝")).toBeInTheDocument();
    expect(screen.getByText("世界骨架初始化完成")).toBeInTheDocument();
    expect(screen.getAllByText("node_committed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("trace: trace-1").length).toBeGreaterThan(0);
  });

  it("filters telemetry by agent", () => {
    render(<TelemetryPanel events={sprint6TelemetryFixture} isRunning />);

    fireEvent.change(screen.getByLabelText("Agent 过滤"), {
      target: { value: "gate_keeper" },
    });

    expect(screen.getByText("1 / 1 / 3 条事件")).toBeInTheDocument();
    expect(screen.getByText("候选事件被边界层拒绝")).toBeInTheDocument();
    expect(screen.queryByText("世界骨架初始化完成")).not.toBeInTheDocument();
  });
});
