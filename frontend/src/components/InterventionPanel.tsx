import { useState, type FormEvent, useEffect, useRef } from "react";

interface InterventionPanelProps {
  context: string;
  onSubmit: (instruction: string) => void;
  onSkip: () => void;
}

const QUICK_ACTIONS = [
  "让主角做出艰难选择",
  "引入神秘第三方",
  "局势急剧恶化",
  "有人背叛立场",
];

export function InterventionPanel({
  context,
  onSubmit,
  onSkip,
}: InterventionPanelProps) {
  const [instruction, setInstruction] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // 自动聚焦
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }, []);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (instruction.trim()) {
      onSubmit(instruction.trim());
      setInstruction("");
    } else {
      onSkip(); // 如果为空提交，则自然推进
    }
  };

  const handleQuick = (action: string) => {
    onSubmit(action);
  };

  return (
    <div
      style={{
        position: "sticky",
        bottom: 24,
        margin: "0 auto",
        width: "min(100%, 720px)",
        background: "rgba(255, 255, 255, 0.85)",
        backdropFilter: "blur(16px)",
        borderRadius: 8,
        border: "1px solid var(--color-accent)",
        padding: "12px 16px",
        zIndex: 50,
        boxShadow: "0 12px 32px rgba(139, 92, 246, 0.15)",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 12,
        }}
      >
        <span
          className="animate-pulse-dot"
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "var(--color-accent)",
            display: "inline-block",
          }}
        />
        <span
          style={{
            fontWeight: 800,
            color: "var(--color-accent)",
            letterSpacing: "0.02em",
          }}
        >
          剧情引导 (Plot Guide)
        </span>
        <span
          title={context}
          style={{
            color: "var(--color-text-secondary)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
            marginLeft: 8,
          }}
        >
          {context}
        </span>
      </div>

      <form
        onSubmit={handleSubmit}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <span style={{ color: "var(--color-accent)", fontWeight: "bold" }}>{">"}</span>
        <input
          ref={inputRef}
          type="text"
          className="input"
          placeholder="输入神谕干预世界，或直接按回车自然推进..."
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          style={{
            flex: 1,
            border: "none",
            background: "transparent",
            padding: 0,
            fontSize: 15,
            boxShadow: "none",
            outline: "none",
          }}
        />
        <button
          type="submit"
          className="btn"
          style={{
            fontSize: 12,
            padding: "6px 12px",
            background: instruction.trim() ? "var(--color-accent)" : "transparent",
            color: instruction.trim() ? "#fff" : "var(--color-text-muted)",
            borderColor: instruction.trim() ? "var(--color-accent)" : "var(--color-border)",
          }}
        >
          {instruction.trim() ? "引导" : "推进 ↵"}
        </button>
      </form>

      <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
        <span className="label" style={{ alignSelf: "center", marginRight: 4 }}>快速:</span>
        {QUICK_ACTIONS.map((action, i) => (
          <button
            key={i}
            className="btn btn-ghost"
            style={{
              fontSize: 11,
              padding: "4px 8px",
              background: "var(--color-bg)",
              color: "var(--color-text-secondary)",
              whiteSpace: "nowrap",
            }}
            onClick={() => handleQuick(action)}
          >
            {action}
          </button>
        ))}
      </div>
    </div>
  );
}
