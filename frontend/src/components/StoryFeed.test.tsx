import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StoryNode } from "../types";
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

describe("StoryFeed", () => {
  it("prioritizes rendered prose and folds logic details", () => {
    const { container } = render(
      <StoryFeed
        nodes={[buildNode()]}
        isRunning={false}
        branchingEnabled={false}
        activeBranchId="main"
        onForkNode={vi.fn()}
      />
    );

    expect(screen.getByText("阿璃在潮雾中停步。")).toBeInTheDocument();
    expect(screen.getByText("逻辑摘要")).toBeInTheDocument();
    const text = container.textContent ?? "";
    expect(text.indexOf("阿璃在潮雾中停步。")).toBeLessThan(
      text.indexOf("逻辑摘要")
    );
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

    expect(screen.getByText("SceneScript")).toBeInTheDocument();
    expect(screen.getByText("GM 结算后的场景摘要。")).toBeInTheDocument();
  });
});
