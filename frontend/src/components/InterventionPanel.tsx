import { useState } from "react";

interface InterventionPanelProps {
  context: string;
  onSubmit: (instruction: string) => void;
  onSkip: () => void;
}

const QUICK_ACTIONS = [
  "让主角在这里做出一个艰难的选择",
  "引入一个神秘的第三方势力",
  "让局势急剧恶化，推向高潮",
  "让某个角色背叛原来的立场",
  "按照故事自然发展，不干预",
];

export function InterventionPanel({ context, onSubmit, onSkip }: InterventionPanelProps) {
  const [instruction, setInstruction] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (instruction.trim()) {
      onSubmit(instruction.trim());
      setInstruction("");
    }
  };

  const handleQuick = (action: string) => {
    if (action === "按照故事自然发展，不干预") {
      onSkip();
    } else {
      onSubmit(action);
    }
  };

  return (
    <div
      style={{
        position: "sticky",
        bottom: 0,
        background: "var(--color-bg-card)",
        borderTop: "2px solid var(--color-warning)",
        padding: "20px 24px",
        zIndex: 50,
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <span
          className="animate-pulse-dot"
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "var(--color-warning)",
            display: "inline-block",
          }}
        />
        <span style={{ fontWeight: 700, fontSize: 13, color: "var(--color-warning)" }}>
          关键节点 — 等待你的干预
        </span>
      </div>

      {/* Context */}
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

      {/* Quick actions */}
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

      {/* Custom input */}
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: 10 }}>
        <input
          className="input"
          placeholder="或者输入你的干预指令..."
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          style={{ flex: 1 }}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={!instruction.trim()}
          style={{ whiteSpace: "nowrap" }}
        >
          提交干预
        </button>
      </form>
    </div>
  );
}
