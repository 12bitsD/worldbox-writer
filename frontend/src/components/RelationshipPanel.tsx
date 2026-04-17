import type { RelationshipLabel, WorldData } from "../types";

interface RelationshipPanelProps {
  world: WorldData | null;
}

const EDGE_COLOR: Record<RelationshipLabel, string> = {
  ally: "#059669",
  trust: "#0f766e",
  neutral: "#9ca3af",
  rival: "#dc2626",
  fear: "#d97706",
  unknown: "#6b7280",
};

export function RelationshipPanel({ world }: RelationshipPanelProps) {
  if (!world) {
    return (
      <div className="card card-sm">
        <div className="label" style={{ marginBottom: 8 }}>
          关系图谱
        </div>
        <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          世界初始化后将显示角色关系。
        </div>
      </div>
    );
  }

  const nodes = world.characters.slice(0, 6);
  const center = 110;
  const radius = 72;
  const nodePositions = nodes.map((char, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1) - Math.PI / 2;
    return {
      id: char.id,
      name: char.name,
      x: center + radius * Math.cos(angle),
      y: center + radius * Math.sin(angle),
    };
  });

  const visibleIds = new Set(nodePositions.map((node) => node.id));
  const edges: Array<{
    from: string;
    to: string;
    label: RelationshipLabel;
    affinity: number;
    note: string;
  }> = [];
  const seen = new Set<string>();

  for (const char of nodes) {
    for (const [targetId, rel] of Object.entries(char.relationships)) {
      if (!visibleIds.has(targetId)) continue;
      const key = [char.id, targetId].sort().join(":");
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push({
        from: char.id,
        to: targetId,
        label: rel.label,
        affinity: rel.affinity,
        note: rel.note,
      });
    }
  }

  const positionMap = Object.fromEntries(nodePositions.map((node) => [node.id, node]));

  return (
    <div className="card" style={{ padding: 16 }}>
      <div className="label" style={{ marginBottom: 10 }}>
        关系图谱
      </div>

      <div
        style={{
          border: "1px solid var(--color-border)",
          background: "linear-gradient(180deg, rgba(255,255,255,0.45), rgba(0,0,0,0.02))",
          padding: 12,
          marginBottom: 12,
        }}
      >
        <svg viewBox="0 0 220 220" style={{ width: "100%", display: "block" }}>
          {edges.map((edge, index) => {
            const from = positionMap[edge.from];
            const to = positionMap[edge.to];
            if (!from || !to) return null;
            return (
              <g key={`${edge.from}-${edge.to}-${index}`}>
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke={EDGE_COLOR[edge.label]}
                  strokeWidth={Math.max(1.5, Math.min(4, Math.abs(edge.affinity) / 20 + 1.5))}
                  opacity={0.85}
                />
              </g>
            );
          })}

          {nodePositions.map((node) => (
            <g key={node.id}>
              <circle
                cx={node.x}
                cy={node.y}
                r={16}
                fill="var(--color-bg-card)"
                stroke="var(--color-text)"
                strokeWidth={1.5}
              />
              <text
                x={node.x}
                y={node.y + 4}
                textAnchor="middle"
                fontSize="10"
                fill="var(--color-text)"
                fontWeight="700"
              >
                {node.name.slice(0, 2)}
              </text>
            </g>
          ))}
        </svg>
      </div>

      {edges.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          当前推演尚未生成明确的人际关系边。
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {edges.slice(0, 6).map((edge, index) => {
            const from = world.characters.find((char) => char.id === edge.from);
            const to = world.characters.find((char) => char.id === edge.to);
            return (
              <div key={`${edge.from}-${edge.to}-${index}`} className="card card-sm">
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 4,
                    gap: 8,
                  }}
                >
                  <span style={{ fontWeight: 700, fontSize: 12 }}>
                    {from?.name} × {to?.name}
                  </span>
                  <span
                    style={{
                      fontSize: 10,
                      padding: "1px 6px",
                      border: `1px solid ${EDGE_COLOR[edge.label]}`,
                      color: EDGE_COLOR[edge.label],
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                    }}
                  >
                    {edge.label}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>
                  关系强度：{edge.affinity}
                </div>
                {edge.note && (
                  <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginTop: 4 }}>
                    {edge.note}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
