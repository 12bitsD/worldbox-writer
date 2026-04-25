import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InterventionPanel } from "./InterventionPanel";

afterEach(() => cleanup());

const context = "第一幕结尾，阿璃已经发现断桥下的潮雾并非自然现象。";

describe("InterventionPanel", () => {
  it("renders the ghost command line and context", () => {
    const onSubmit = vi.fn();
    const onSkip = vi.fn();

    render(
      <InterventionPanel
        context={context}
        onSubmit={onSubmit}
        onSkip={onSkip}
      />
    );

    expect(screen.getByText("剧情引导 (Plot Guide)")).toBeInTheDocument();
    expect(screen.getByText(context)).toBeInTheDocument();
  });

  it("submits empty form to naturally progress (skip)", () => {
    const onSkip = vi.fn();

    render(
      <InterventionPanel
        context={context}
        onSubmit={vi.fn()}
        onSkip={onSkip}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "推进 ↵" }));

    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it("submits custom instruction", () => {
    const onSubmit = vi.fn();

    render(
      <InterventionPanel
        context={context}
        onSubmit={onSubmit}
        onSkip={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("输入神谕干预世界，或直接按回车自然推进...");
    fireEvent.change(input, {
      target: { value: "让阿璃主动踏入潮雾并付出代价" },
    });
    
    // The button text changes when there is input
    fireEvent.click(screen.getByRole("button", { name: "引导" }));

    expect(onSubmit).toHaveBeenCalledWith("让阿璃主动踏入潮雾并付出代价");
  });

  it("submits quick action immediately", () => {
    const onSubmit = vi.fn();

    render(
      <InterventionPanel
        context={context}
        onSubmit={onSubmit}
        onSkip={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "局势急剧恶化" }));

    expect(onSubmit).toHaveBeenCalledWith("局势急剧恶化");
  });
});
