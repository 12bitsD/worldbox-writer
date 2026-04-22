import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InterventionPanel } from "./InterventionPanel";

afterEach(() => cleanup());

const context = "第一幕结尾，阿璃已经发现断桥下的潮雾并非自然现象。";

describe("InterventionPanel", () => {
  it("keeps the waiting state as a compact reading bar", () => {
    const onSubmit = vi.fn();
    const onSkip = vi.fn();

    render(
      <InterventionPanel
        context={context}
        onSubmit={onSubmit}
        onSkip={onSkip}
      />
    );

    expect(screen.getByText("关键节点")).toBeInTheDocument();
    expect(screen.getByText(context)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "自然推进" }));

    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it("opens intervention controls on demand and submits custom guidance", () => {
    const onSubmit = vi.fn();

    render(
      <InterventionPanel
        context={context}
        onSubmit={onSubmit}
        onSkip={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "干预" }));
    expect(screen.getByRole("dialog", { name: "关键节点干预" })).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("输入你的干预指令..."), {
      target: { value: "让阿璃主动踏入潮雾并付出代价" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交干预" }));

    expect(onSubmit).toHaveBeenCalledWith("让阿璃主动踏入潮雾并付出代价");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("moves setting edits into the drawer instead of stacking another panel", () => {
    render(
      <InterventionPanel
        context={context}
        onSubmit={vi.fn()}
        onSkip={vi.fn()}
        editPanel={<div>设定编辑内容</div>}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "编辑设定" }));

    expect(screen.getByRole("dialog", { name: "关键节点干预" })).toBeInTheDocument();
    expect(screen.getByText("设定编辑内容")).toBeInTheDocument();
  });
});
