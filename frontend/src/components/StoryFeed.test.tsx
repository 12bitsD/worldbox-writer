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
