import type { WorldData } from "../types";

interface WorldPanelProps {
  world: WorldData;
}

export function WorldPanel({ world }: WorldPanelProps) {
  const activeBranchId = world.active_branch_id ?? "main";
  const branches = world.branches ?? {};
  const characters = world.characters ?? [];
  const factions = world.factions ?? [];
  const constraints = world.constraints ?? [];
  const worldRules = world.world_rules ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* World title */}
      <div className="card">
        <div className="label" style={{ marginBottom: 8 }}>
          世界
        </div>
        <div className="display-md" style={{ fontSize: 22, marginBottom: 6 }}>
          {world.title || "未命名世界"}
        </div>
        <p style={{ fontSize: 12, color: "var(--color-text-secondary)", lineHeight: 1.5 }}>
          {world.premise}
        </p>
        <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span
            style={{
              fontSize: 10,
              padding: "2px 8px",
              border: "1px solid var(--color-warning)",
              color: "var(--color-warning)",
              textTransform: "uppercase",
            }}
          >
            active: {activeBranchId}
          </span>
          <span
            style={{
              fontSize: 10,
              padding: "2px 8px",
              border: "1px solid var(--color-border)",
              color: "var(--color-text-muted)",
            }}
          >
            {branches[activeBranchId]?.label ?? "Main Timeline"}
          </span>
        </div>
        <div className="divider" />
        <div style={{ display: "flex", gap: 24 }}>
          <div>
            <div className="label">当前时间轴</div>
            <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2 }}>T{world.tick}</div>
          </div>
          <div>
            <div className="label">角色数量</div>
            <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2 }}>
              {characters.length}
            </div>
          </div>
          <div>
            <div className="label">势力数量</div>
            <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2 }}>
              {factions.length}
            </div>
          </div>
        </div>
      </div>

      {/* Characters */}
      <div>
        <div className="label" style={{ marginBottom: 10 }}>
          角色
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {characters.map((char, i) => {
            const goals = char.goals ?? [];
            const memory = char.memory ?? [];
            return (
              <div key={char.id} className="card card-sm numbered-item">
                <span className="number">{String(i + 1).padStart(2, "0")}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span style={{ fontWeight: 700, fontSize: 13 }}>{char.name}</span>
                    <span
                      style={{
                        fontSize: 10,
                        padding: "1px 6px",
                        border: "1px solid var(--color-border)",
                        color: "var(--color-text-muted)",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                      }}
                    >
                      {char.status}
                    </span>
                  </div>
                  <p style={{ fontSize: 11, color: "var(--color-text-secondary)", marginBottom: 4 }}>
                    {char.personality}
                  </p>
                  {goals.length > 0 && (
                    <p style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
                      目标：{goals.slice(0, 2).join(" / ")}
                    </p>
                  )}
                  {memory.length > 0 && (
                    <div
                      style={{
                        marginTop: 6,
                        padding: "4px 8px",
                        background: "var(--color-bg)",
                        borderLeft: "2px solid var(--color-border)",
                        fontSize: 11,
                        color: "var(--color-text-muted)",
                      }}
                    >
                      {memory[memory.length - 1]}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Constraints */}
      {constraints.length > 0 && (
        <div>
          <div className="label" style={{ marginBottom: 10 }}>
            世界约束
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {constraints.map((c, i) => (
              <div
                key={i}
                className="card card-sm"
                style={{
                  borderLeft: `3px solid ${
                    c.severity === "hard"
                      ? "var(--color-danger)"
                      : "var(--color-warning)"
                  }`,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                  <span style={{ fontWeight: 600, fontSize: 12 }}>{c.name}</span>
                  <span
                    style={{
                      fontSize: 10,
                      color:
                        c.severity === "hard"
                          ? "var(--color-danger)"
                          : "var(--color-warning)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                    }}
                  >
                    {c.severity}
                  </span>
                </div>
                <p style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>{c.rule}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* World rules */}
      {worldRules.length > 0 && (
        <div>
          <div className="label" style={{ marginBottom: 10 }}>
            世界规则
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {worldRules.slice(0, 5).map((rule, i) => (
              <div key={i} className="numbered-item" style={{ padding: "6px 0" }}>
                <span className="number">{String(i + 1).padStart(2, "0")}</span>
                <span style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>{rule}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
