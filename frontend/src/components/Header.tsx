import type { SimStatus } from "../types";

interface HeaderProps {
  status: SimStatus | null;
  onReset: () => void;
}

const statusLabel: Record<SimStatus, string> = {
  initializing: "初始化中",
  running: "推演中",
  waiting: "等待干预",
  complete: "已完成",
  error: "错误",
};

export function Header({ status, onReset }: HeaderProps) {
  return (
    <header
      style={{
        borderBottom: "1px solid var(--color-border)",
        padding: "0 32px",
        height: 52,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "var(--color-bg-card)",
        position: "sticky",
        top: 0,
        zIndex: 100,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span
          style={{
            fontSize: 13,
            fontWeight: 800,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          WORLDBOX WRITER
        </span>
        <span style={{ color: "var(--color-border)", fontSize: 12 }}>|</span>
        <span className="label">Agent 集群小说创作系统</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {status && (
          <span className={`badge badge-${status}`}>
            {status === "running" && (
              <span
                className="animate-pulse-dot"
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: "currentColor",
                  display: "inline-block",
                }}
              />
            )}
            {statusLabel[status]}
          </span>
        )}
        {status && (
          <button className="btn btn-ghost" onClick={onReset}>
            重置
          </button>
        )}
      </div>
    </header>
  );
}
