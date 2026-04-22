import { useState, type FormEvent, type ReactNode } from "react";

interface InterventionPanelProps {
  context: string;
  onSubmit: (instruction: string) => void;
  onSkip: () => void;
  editPanel?: ReactNode;
}

const QUICK_ACTIONS = [
  "让主角在这里做出一个艰难的选择",
  "引入一个神秘的第三方势力",
  "让局势急剧恶化，推向高潮",
  "让某个角色背叛原来的立场",
  "按照故事自然发展，不干预",
];

type DrawerTab = "intervention" | "edit";

function compactContext(context: string): string {
  const text = context.replace(/\s+/g, " ").trim();
  if (text.length <= 92) return text;
  return `${text.slice(0, 91).trim()}...`;
}

export function InterventionPanel({
  context,
  onSubmit,
  onSkip,
  editPanel,
}: InterventionPanelProps) {
  const [instruction, setInstruction] = useState("");
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<DrawerTab>("intervention");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (instruction.trim()) {
      onSubmit(instruction.trim());
      setInstruction("");
      setIsDrawerOpen(false);
    }
  };

  const handleQuick = (action: string) => {
    if (action === "按照故事自然发展，不干预") {
      onSkip();
    } else {
      onSubmit(action);
    }
    setIsDrawerOpen(false);
  };

  const openDrawer = (tab: DrawerTab) => {
    setActiveTab(tab);
    setIsDrawerOpen(true);
  };

  return (
    <>
      <div
        style={{
          position: "sticky",
          bottom: 0,
          background: "rgba(249, 248, 245, 0.96)",
          backdropFilter: "blur(10px)",
          borderTop: "1px solid rgba(230, 126, 34, 0.35)",
          padding: "10px 16px",
          zIndex: 50,
          boxShadow: "0 -8px 24px rgba(17, 17, 17, 0.06)",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) auto",
            gap: 12,
            alignItems: "center",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 2,
              }}
            >
              <span
                className="animate-pulse-dot"
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  background: "var(--color-warning)",
                  display: "inline-block",
                }}
              />
              <span
                style={{
                  fontWeight: 800,
                  fontSize: 12,
                  color: "var(--color-warning)",
                  letterSpacing: "0.02em",
                }}
              >
                关键节点
              </span>
            </div>
            <div
              title={context}
              style={{
                fontSize: 12,
                color: "var(--color-text-secondary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {compactContext(context)}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              className="btn btn-primary"
              style={{ fontSize: 12, padding: "7px 12px" }}
              onClick={() => openDrawer("intervention")}
            >
              干预
            </button>
            {editPanel && (
              <button
                className="btn"
                style={{ fontSize: 12, padding: "7px 12px" }}
                onClick={() => openDrawer("edit")}
              >
                编辑设定
              </button>
            )}
            <button
              className="btn"
              style={{ fontSize: 12, padding: "7px 12px" }}
              onClick={onSkip}
            >
              自然推进
            </button>
          </div>
        </div>
      </div>

      {isDrawerOpen && (
        <aside
          role="dialog"
          aria-label="关键节点干预"
          style={{
            position: "fixed",
            top: 68,
            right: 16,
            bottom: 16,
            width: "min(460px, calc(100vw - 32px))",
            zIndex: 90,
            background: "var(--color-bg-card)",
            border: "1px solid var(--color-border)",
            boxShadow: "0 18px 48px rgba(17, 17, 17, 0.18)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div
            style={{
              padding: "14px 16px",
              borderBottom: "1px solid var(--color-border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            <div>
              <div className="label" style={{ marginBottom: 4 }}>
                关键节点
              </div>
              <div style={{ fontWeight: 800, fontSize: 14 }}>
                等待你的干预
              </div>
            </div>
            <button
              className="btn btn-ghost"
              onClick={() => setIsDrawerOpen(false)}
            >
              关闭
            </button>
          </div>

          <div
            style={{
              display: "flex",
              gap: 8,
              padding: "10px 16px",
              borderBottom: "1px solid var(--color-border-light)",
            }}
          >
            <button
              className={activeTab === "intervention" ? "btn btn-primary" : "btn"}
              style={{ fontSize: 12, padding: "6px 10px" }}
              onClick={() => setActiveTab("intervention")}
            >
              干预指令
            </button>
            {editPanel && (
              <button
                className={activeTab === "edit" ? "btn btn-primary" : "btn"}
                style={{ fontSize: 12, padding: "6px 10px" }}
                onClick={() => setActiveTab("edit")}
              >
                设定编辑
              </button>
            )}
          </div>

          <div style={{ overflowY: "auto", padding: 16 }}>
            {activeTab === "intervention" && (
              <>
                <div
                  style={{
                    padding: "10px 14px",
                    background: "rgba(230, 126, 34, 0.06)",
                    border: "1px solid rgba(230, 126, 34, 0.2)",
                    marginBottom: 14,
                    fontSize: 13,
                    lineHeight: 1.6,
                    color: "var(--color-text-secondary)",
                  }}
                >
                  {context}
                </div>

                <div style={{ marginBottom: 12 }}>
                  <div className="label" style={{ marginBottom: 8 }}>
                    快速干预
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {QUICK_ACTIONS.map((action, i) => (
                      <button
                        key={i}
                        className="btn"
                        style={{ fontSize: 11, padding: "4px 10px" }}
                        onClick={() => handleQuick(action)}
                      >
                        {action}
                      </button>
                    ))}
                  </div>
                </div>

                <form
                  onSubmit={handleSubmit}
                  style={{ display: "flex", flexDirection: "column", gap: 10 }}
                >
                  <textarea
                    className="input textarea"
                    placeholder="输入你的干预指令..."
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    style={{ minHeight: 96 }}
                  />
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={!instruction.trim()}
                    style={{ justifyContent: "center" }}
                  >
                    提交干预
                  </button>
                </form>
              </>
            )}

            {activeTab === "edit" && editPanel}
          </div>
        </aside>
      )}
    </>
  );
}
