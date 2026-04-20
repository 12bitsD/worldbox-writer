import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ExportPanel } from "./ExportPanel";

describe("ExportPanel", () => {
  it("renders the rich export bundle once data is generated", async () => {
    const onExport = vi.fn().mockResolvedValue({
      sim_id: "sim-1",
      branch_id: "main",
      generated_at: "2026-04-19T00:00:00+00:00",
      summary: {
        node_count: 2,
        rendered_node_count: 2,
        character_count: 1,
        rule_count: 1,
        faction_count: 0,
        location_count: 0,
      },
      manifest: {
        bundle_name: "bundle",
        generated_at: "2026-04-19T00:00:00+00:00",
        sim_id: "sim-1",
        branch_id: "main",
        files: [
          { kind: "novel_txt", filename: "bundle.txt", mime_type: "text/plain" },
          { kind: "novel_markdown", filename: "bundle.md", mime_type: "text/markdown" },
          { kind: "novel_html", filename: "bundle.html", mime_type: "text/html" },
          {
            kind: "novel_docx",
            filename: "bundle.docx",
            mime_type:
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          },
          { kind: "novel_pdf", filename: "bundle.pdf", mime_type: "application/pdf" },
          {
            kind: "world_settings_json",
            filename: "bundle-settings.json",
            mime_type: "application/json",
          },
          {
            kind: "timeline_json",
            filename: "bundle-timeline.json",
            mime_type: "application/json",
          },
          {
            kind: "manifest_json",
            filename: "bundle-manifest.json",
            mime_type: "application/json",
          },
        ],
      },
      novel: "正文",
      markdown: "# 正文",
      html: "<html><body><p>正文</p></body></html>",
      world_settings: {
        title: "标题",
        premise: "前提",
        world_rules: ["规则一"],
        factions: [],
        locations: [],
        characters: [
          {
            name: "角色A",
            description: "角色简介",
            personality: "沉着",
            goals: ["守城"],
            status: "alive",
          },
        ],
      },
      timeline: [
        {
          tick: 1,
          title: "开场",
          type: "setup",
          description: "故事开始",
          branch_id: "main",
        },
      ],
    });

    render(<ExportPanel simId="sim-1" onExport={onExport} />);

    fireEvent.click(screen.getByRole("button", { name: "生成导出内容" }));

    await waitFor(() => expect(onExport).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("button", { name: "下载 Markdown" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下载清单" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "排版稿" }));
    expect(screen.getByRole("button", { name: "下载 HTML" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下载 DOCX" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下载 PDF" })).toBeInTheDocument();
  });
});
