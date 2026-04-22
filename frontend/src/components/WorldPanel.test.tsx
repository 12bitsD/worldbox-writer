import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { WorldData } from "../types";
import { WorldPanel } from "./WorldPanel";

afterEach(() => cleanup());

describe("WorldPanel", () => {
  it("renders a normal world summary", () => {
    render(
      <WorldPanel
        world={{
          title: "断桥世界",
          premise: "潮雾吞没旧城。",
          tick: 3,
          is_complete: false,
          characters: [
            {
              id: "char-1",
              name: "阿璃",
              description: "",
              personality: "谨慎",
              goals: ["找到断桥"],
              status: "alive",
              memory: ["潮雾出现"],
              relationships: {},
            },
          ],
          factions: [],
          locations: [],
          world_rules: ["行动必须付出代价"],
          constraints: [],
          branches: { main: { label: "主线", forked_from_node: null } },
          active_branch_id: "main",
        }}
      />
    );

    expect(screen.getByText("断桥世界")).toBeInTheDocument();
    expect(screen.getByText("阿璃")).toBeInTheDocument();
    expect(screen.getByText("主线")).toBeInTheDocument();
  });

  it("tolerates legacy world payloads without branch metadata", () => {
    const legacyWorld = {
      title: "旧世界",
      premise: "旧会话缺少分支字段。",
      tick: 1,
      is_complete: false,
      characters: [],
      factions: [],
      locations: [],
      world_rules: [],
      constraints: [],
    } as unknown as WorldData;

    render(<WorldPanel world={legacyWorld} />);

    expect(screen.getByText("旧世界")).toBeInTheDocument();
    expect(screen.getByText("active: main")).toBeInTheDocument();
    expect(screen.getByText("Main Timeline")).toBeInTheDocument();
  });
});
