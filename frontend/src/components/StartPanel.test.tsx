import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StartPanel } from "./StartPanel";

afterEach(() => cleanup());

describe("StartPanel", () => {
  it("submits from the visible start button", () => {
    const onStart = vi.fn();

    render(
      <StartPanel
        onStart={onStart}
        onOpenSession={vi.fn()}
        recentSessions={[]}
        loading={false}
      />
    );

    fireEvent.change(screen.getByPlaceholderText("描述你的故事世界和主角，一句话即可..."), {
      target: { value: "末日后的地下城市，三个势力争夺最后的净水源" },
    });
    fireEvent.click(screen.getByRole("button", { name: "开始推演 →" }));

    expect(onStart).toHaveBeenCalledWith(
      "末日后的地下城市，三个势力争夺最后的净水源",
      8
    );
  });

  it("opens recent sessions and shows their error reason", () => {
    const onOpenSession = vi.fn();

    render(
      <StartPanel
        onStart={vi.fn()}
        onOpenSession={onOpenSession}
        loading={false}
        recentSessions={[
          {
            sim_id: "failed-1",
            status: "error",
            premise: "失败前提",
            nodes_count: 0,
            error: "Server restarted during simulation",
          },
        ]}
      />
    );

    expect(screen.getByText("错误原因：Server restarted during simulation")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /failed-1/ }));

    expect(onOpenSession).toHaveBeenCalledWith("failed-1");
  });
});
