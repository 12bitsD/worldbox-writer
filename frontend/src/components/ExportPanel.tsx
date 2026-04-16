import { useState } from "react";
import type { ExportData } from "../types";

interface ExportPanelProps {
  simId: string;
  onExport: () => Promise<ExportData | null>;
}

export function ExportPanel({ simId, onExport }: ExportPanelProps) {
  const [data, setData] = useState<ExportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"novel" | "settings" | "timeline">("novel");

  const handleExport = async () => {
    setLoading(true);
    const result = await onExport();
    if (result) setData(result);
    setLoading(false);
  };

  const downloadText = (content: string, filename: string) => {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadJSON = (content: object, filename: string) => {
    const blob = new Blob([JSON.stringify(content, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!data) {
    return (
      <div className="card" style={{ textAlign: "center", padding: 32 }}>
        <div className="display-md" style={{ fontSize: 20, marginBottom: 8 }}>
          故事已完成
        </div>
        <p style={{ color: "var(--color-text-secondary)", fontSize: 13, marginBottom: 20 }}>
          导出完整小说文本、世界设定集和故事时间线
        </p>
        <button
          className="btn btn-primary"
          onClick={handleExport}
          disabled={loading}
          style={{ padding: "10px 24px" }}
        >
          {loading ? "生成导出数据..." : "生成导出内容"}
        </button>
      </div>
    );
  }

  const tabs: Array<{ key: typeof activeTab; label: string }> = [
    { key: "novel", label: "小说正文" },
    { key: "settings", label: "世界设定" },
    { key: "timeline", label: "故事时间线" },
  ];

  return (
    <div className="card" style={{ padding: 0 }}>
      {/* Tab bar */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid var(--color-border)",
          padding: "0 16px",
        }}
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className="btn btn-ghost"
            style={{
              borderBottom: activeTab === tab.key ? "2px solid var(--color-text)" : "2px solid transparent",
              borderRadius: 0,
              padding: "12px 16px",
              fontSize: 12,
              fontWeight: activeTab === tab.key ? 700 : 400,
            }}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          {activeTab === "novel" && (
            <button
              className="btn"
              style={{ fontSize: 11, padding: "4px 10px" }}
              onClick={() => downloadText(data.novel, `worldbox-${simId}-novel.txt`)}
            >
              下载 TXT
            </button>
          )}
          {activeTab === "settings" && (
            <button
              className="btn"
              style={{ fontSize: 11, padding: "4px 10px" }}
              onClick={() => downloadJSON(data.world_settings, `worldbox-${simId}-settings.json`)}
            >
              下载 JSON
            </button>
          )}
          {activeTab === "timeline" && (
            <button
              className="btn"
              style={{ fontSize: 11, padding: "4px 10px" }}
              onClick={() => downloadJSON(data.timeline, `worldbox-${simId}-timeline.json`)}
            >
              下载 JSON
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div style={{ padding: 20, maxHeight: 500, overflowY: "auto" }}>
        {activeTab === "novel" && (
          <pre
            style={{
              fontFamily: "inherit",
              fontSize: 13,
              lineHeight: 1.8,
              whiteSpace: "pre-wrap",
              color: "var(--color-text)",
            }}
          >
            {data.novel}
          </pre>
        )}

        {activeTab === "settings" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <div className="label" style={{ marginBottom: 8 }}>
                世界规则
              </div>
              {data.world_settings.world_rules.map((r, i) => (
                <div key={i} className="numbered-item" style={{ marginBottom: 6 }}>
                  <span className="number">{String(i + 1).padStart(2, "0")}</span>
                  <span style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>{r}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="label" style={{ marginBottom: 8 }}>
                角色档案
              </div>
              {data.world_settings.characters.map((c, i) => (
                <div key={i} className="card card-sm" style={{ marginBottom: 8 }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>{c.name}</div>
                  <div style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
                    {c.personality}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginTop: 4 }}>
                    目标：{c.goals.join(" / ")}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "timeline" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
            {data.timeline.map((item, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  gap: 16,
                  paddingBottom: 16,
                  paddingLeft: 8,
                  borderLeft: "1px solid var(--color-border)",
                  marginLeft: 8,
                  position: "relative",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    left: -5,
                    top: 4,
                    width: 9,
                    height: 9,
                    borderRadius: "50%",
                    background: "var(--color-bg-card)",
                    border: "2px solid var(--color-border)",
                  }}
                />
                <div style={{ paddingLeft: 16 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                    <span style={{ fontSize: 11, color: "var(--color-text-muted)" }}>T{item.tick}</span>
                    <span style={{ fontWeight: 700, fontSize: 13 }}>{item.title}</span>
                    <span
                      style={{
                        fontSize: 10,
                        padding: "1px 5px",
                        border: "1px solid var(--color-border)",
                        color: "var(--color-text-muted)",
                        textTransform: "uppercase",
                      }}
                    >
                      {item.type}
                    </span>
                  </div>
                  <p style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
                    {item.description}
                  </p>
                  {item.intervention && (
                    <p
                      style={{
                        fontSize: 11,
                        color: "var(--color-warning)",
                        marginTop: 4,
                      }}
                    >
                      干预：{item.intervention}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
