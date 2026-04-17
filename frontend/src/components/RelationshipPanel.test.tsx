import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RelationshipPanel } from "./RelationshipPanel";
import { sprint6WorldFixture } from "../test/sprint6-fixtures";

describe("RelationshipPanel", () => {
  it("renders the empty state before world initialization", () => {
    render(<RelationshipPanel world={null} />);

    expect(screen.getByText("关系图谱")).toBeInTheDocument();
    expect(screen.getByText("世界初始化后将显示角色关系。")).toBeInTheDocument();
  });

  it("renders relationship edges from Sprint 6 fixtures", () => {
    render(<RelationshipPanel world={sprint6WorldFixture} />);

    expect(screen.getByText("阿璃 × 白夜")).toBeInTheDocument();
    expect(screen.getByText("白夜 × 赤霄")).toBeInTheDocument();
    expect(screen.getByText("关系强度：20")).toBeInTheDocument();
    expect(screen.getByText("关系强度：-25")).toBeInTheDocument();
    expect(screen.getByText("在断桥下暂时结盟。")).toBeInTheDocument();
    expect(screen.getByText("赤霄在雨夜中发动袭击。")).toBeInTheDocument();
  });
});
