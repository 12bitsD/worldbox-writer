import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TelemetryPanel } from "./TelemetryPanel";
import { sprint6TelemetryFixture } from "../test/sprint6-fixtures";

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

    expect(screen.getByText("3 条事件")).toBeInTheDocument();
    expect(screen.getByText("新故事节点已固化")).toBeInTheDocument();
    expect(screen.getByText("候选事件被边界层拒绝")).toBeInTheDocument();
    expect(screen.getByText("世界骨架初始化完成")).toBeInTheDocument();
    expect(screen.getByText("node_committed")).toBeInTheDocument();
    expect(screen.getByText('{"node_id":"node-3"}')).toBeInTheDocument();
  });
});
