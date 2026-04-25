import { useState } from "react";

import type { RelationshipLabel, WorldData } from "../types";
import { updateRelationship } from "../utils/api";

interface RelationshipPanelProps {
  world: WorldData | null;
  simId?: string | null;
  isRunning?: boolean;
  onUpdated?: () => void;
}

const EDGE_COLOR: Record<RelationshipLabel, string> = {
  ally: "#059669",
  trust: "#0f766e",
  neutral: "#9ca3af",
  rival: "#dc2626",
  fear: "#d97706",
  unknown: "#6b7280",
};

const RELATIONSHIP_LABELS: RelationshipLabel[] = [
  "ally",
  "trust",
  "neutral",
  "rival",
  "fear",
  "unknown",
];

export function RelationshipPanel({
  world,
  simId,
  isRunning = false,
  onUpdated,
}: RelationshipPanelProps) {
  const [focusedCharacterId, setFocusedCharacterId] = useState<string | null>(null);
  const [selectedEdgeKey, setSelectedEdgeKey] = useState<string | null>(null);
  const [dragSourceId, setDragSourceId] = useState<string | null>(null);
  const [draftEdge, setDraftEdge] = useState<{
    sourceId: string;
    targetId: string;
  } | null>(null);
  const [draftLabel, setDraftLabel] = useState<RelationshipLabel>("rival");
  const [draftAffinity, setDraftAffinity] = useState(-20);
  const [draftNote, setDraftNote] = useState("");
  const [savingEdge, setSavingEdge] = useState(false);
  const [edgeError, setEdgeError] = useState<string | null>(null);

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
    key: string;
    from: string;
    to: string;
    label: RelationshipLabel;
    affinity: number;
    note: string;
    updatedAtTick: number | null;
  }> = [];
  const seen = new Set<string>();

  for (const char of nodes) {
    for (const [targetId, rel] of Object.entries(char.relationships)) {
      if (!visibleIds.has(targetId)) continue;
      const key = [char.id, targetId].sort().join(":");
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push({
        key,
        from: char.id,
        to: targetId,
        label: rel.label,
        affinity: rel.affinity,
        note: rel.note,
        updatedAtTick: rel.updated_at_tick,
      });
    }
  }

  const positionMap = Object.fromEntries(nodePositions.map((node) => [node.id, node]));
  const visibleEdges = focusedCharacterId
    ? edges.filter(
        (edge) => edge.from === focusedCharacterId || edge.to === focusedCharacterId
      )
    : edges;
  const selectedEdge =
    visibleEdges.find((edge) => edge.key === selectedEdgeKey) ?? visibleEdges[0] ?? null;
  const focusedCharacter =
    world.characters.find((char) => char.id === focusedCharacterId) ?? null;
  const canEditGraph = Boolean(simId && onUpdated && !isRunning);
  const draftSource =
    world.characters.find((char) => char.id === draftEdge?.sourceId) ?? null;
  const draftTarget =
    world.characters.find((char) => char.id === draftEdge?.targetId) ?? null;

  const openDraftEdge = (sourceId: string, targetId: string) => {
    const existing =
      world.characters.find((char) => char.id === sourceId)?.relationships[targetId] ??
      null;
    setDraftEdge({ sourceId, targetId });
    setDraftLabel(existing?.label ?? "rival");
    setDraftAffinity(existing?.affinity ?? -20);
    setDraftNote(existing?.note ?? "");
    setEdgeError(null);
  };

  const saveDraftEdge = async () => {
    if (!simId || !draftEdge) return;
    setSavingEdge(true);
    setEdgeError(null);
    try {
      await updateRelationship(simId, {
        source_character_id: draftEdge.sourceId,
        target_character_id: draftEdge.targetId,
        label: draftLabel,
        affinity: draftAffinity,
        note: draftNote,
        bidirectional: true,
      });
      setDraftEdge(null);
      await onUpdated?.();
    } catch (e) {
      setEdgeError(String(e));
    } finally {
      setSavingEdge(false);
    }
  };

  return (
    <div className="card" style={{ padding: 16 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          marginBottom: 10,
        }}
      >
        <div className="label">关系网 (Network)</div>
        {focusedCharacterId && (
          <button
            className="btn"
            style={{ fontSize: 11, padding: "4px 8px" }}
            onClick={() => {
              setFocusedCharacterId(null);
              setSelectedEdgeKey(null);
            }}
          >
            清除聚焦
          </button>
        )}
      </div>

      <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginBottom: 10 }}>
        {canEditGraph
          ? "拖拽一个角色节点到另一个节点，可直接建立或修改关系。"
          : isRunning
            ? "运行中只读；关键节点暂停或完成后可拖拽编辑关系。"
            : "当前会话不可编辑关系。"}
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
          marginBottom: 12,
        }}
      >
        {nodes.map((node) => (
          <button
            key={node.id}
            className={`btn ${focusedCharacterId === node.id ? "btn-primary" : ""}`}
            style={{ fontSize: 11, padding: "4px 8px" }}
            onClick={() => {
              setFocusedCharacterId((prev) => (prev === node.id ? null : node.id));
              setSelectedEdgeKey(null);
            }}
          >
            {node.name}
          </button>
        ))}
      </div>

      <div
        style={{
          border: "1px solid var(--color-border)",
          background:
            "linear-gradient(180deg, rgba(255,255,255,0.45), rgba(0,0,0,0.02))",
          padding: 12,
          marginBottom: 12,
        }}
      >
        <svg viewBox="0 0 220 220" style={{ width: "100%", display: "block" }}>
          {edges.map((edge, index) => {
            const from = positionMap[edge.from];
            const to = positionMap[edge.to];
            if (!from || !to) return null;
            const highlighted =
              !focusedCharacterId ||
              edge.from === focusedCharacterId ||
              edge.to === focusedCharacterId;
            const selected = selectedEdge?.key === edge.key;
            return (
              <g
                key={`${edge.from}-${edge.to}-${index}`}
                onClick={() => setSelectedEdgeKey(edge.key)}
                style={{ cursor: "pointer" }}
              >
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke={EDGE_COLOR[edge.label]}
                  strokeWidth={
                    selected
                      ? 5
                      : Math.max(1.5, Math.min(4, Math.abs(edge.affinity) / 20 + 1.5))
                  }
                  opacity={highlighted ? 0.95 : 0.18}
                />
              </g>
            );
          })}

          {nodePositions.map((node) => {
            const isFocused = focusedCharacterId === node.id;
            const isDimmed = Boolean(focusedCharacterId) && !isFocused;
            return (
              <g
                key={node.id}
                onPointerDown={(event) => {
                  if (!canEditGraph) return;
                  event.stopPropagation();
                  setDragSourceId(node.id);
                }}
                onPointerUp={(event) => {
                  if (!canEditGraph) return;
                  event.stopPropagation();
                  if (dragSourceId && dragSourceId !== node.id) {
                    openDraftEdge(dragSourceId, node.id);
                  }
                  setDragSourceId(null);
                }}
                onClick={() => {
                  setFocusedCharacterId((prev) => (prev === node.id ? null : node.id));
                  setSelectedEdgeKey(null);
                }}
                style={{ cursor: canEditGraph ? "grab" : "pointer" }}
              >
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={isFocused ? 18 : 16}
                  fill="var(--color-bg-card)"
                  stroke="var(--color-text)"
                  strokeWidth={isFocused ? 2.5 : 1.5}
                  opacity={isDimmed ? 0.35 : 1}
                />
                <text
                  x={node.x}
                  y={node.y + 4}
                  textAnchor="middle"
                  fontSize="10"
                  fill="var(--color-text)"
                  fontWeight="700"
                  opacity={isDimmed ? 0.4 : 1}
                >
                  {node.name.slice(0, 2)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {draftEdge && draftSource && draftTarget && (
        <div
          className="card card-sm"
          style={{
            marginBottom: 12,
            borderColor: EDGE_COLOR[draftLabel],
            borderStyle: "dashed",
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 800, marginBottom: 8 }}>
            修改关系：{draftSource.name} → {draftTarget.name}
          </div>
          <label
            style={{
              display: "grid",
              gap: 4,
              fontSize: 11,
              color: "var(--color-text-muted)",
              marginBottom: 8,
            }}
          >
            关系类型
            <select
              value={draftLabel}
              onChange={(event) => setDraftLabel(event.target.value as RelationshipLabel)}
              disabled={savingEdge}
            >
              {RELATIONSHIP_LABELS.map((label) => (
                <option key={label} value={label}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label
            style={{
              display: "grid",
              gap: 4,
              fontSize: 11,
              color: "var(--color-text-muted)",
              marginBottom: 8,
            }}
          >
            关系强度（-100 到 100）
            <input
              type="number"
              min={-100}
              max={100}
              value={draftAffinity}
              onChange={(event) => setDraftAffinity(Number(event.target.value))}
              disabled={savingEdge}
            />
          </label>
          <label
            style={{
              display: "grid",
              gap: 4,
              fontSize: 11,
              color: "var(--color-text-muted)",
              marginBottom: 8,
            }}
          >
            关系说明
            <textarea
              className="input textarea"
              value={draftNote}
              onChange={(event) => setDraftNote(event.target.value)}
              disabled={savingEdge}
              style={{ minHeight: 56, fontSize: 12 }}
            />
          </label>
          {edgeError && (
            <div style={{ fontSize: 11, color: "var(--color-danger)", marginBottom: 8 }}>
              {edgeError}
            </div>
          )}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button
              className="btn"
              style={{ fontSize: 11, padding: "5px 10px" }}
              onClick={() => setDraftEdge(null)}
              disabled={savingEdge}
            >
              取消
            </button>
            <button
              className="btn btn-primary"
              style={{ fontSize: 11, padding: "5px 10px" }}
              onClick={saveDraftEdge}
              disabled={savingEdge}
            >
              {savingEdge ? "保存中..." : "保存关系"}
            </button>
          </div>
        </div>
      )}

      {focusedCharacter && (
        <div className="card card-sm" style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
            当前聚焦：{focusedCharacter.name}
          </div>
          <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>
            目标：{focusedCharacter.goals.join("、") || "暂无"}
          </div>
        </div>
      )}

      {visibleEdges.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          {focusedCharacter
            ? `${focusedCharacter.name} 当前还没有明确的人际关系边。`
            : "当前推演尚未生成明确的人际关系边。"}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {visibleEdges.map((edge) => {
            const from = world.characters.find((char) => char.id === edge.from);
            const to = world.characters.find((char) => char.id === edge.to);
            const isSelected = selectedEdge?.key === edge.key;
            return (
              <button
                key={edge.key}
                type="button"
                className="card card-sm"
                style={{
                  textAlign: "left",
                  borderColor: isSelected ? EDGE_COLOR[edge.label] : "var(--color-border)",
                }}
                onClick={() => setSelectedEdgeKey(edge.key)}
              >
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
              </button>
            );
          })}

          {selectedEdge && (
            <div className="card card-sm" style={{ borderStyle: "dashed" }}>
              <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>
                边详情
              </div>
              <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>
                标签：{selectedEdge.label}
              </div>
              <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginTop: 4 }}>
                强度：{selectedEdge.affinity}
              </div>
              <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginTop: 4 }}>
                最近更新时间：T{selectedEdge.updatedAtTick ?? "?"}
              </div>
              {selectedEdge.note && (
                <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginTop: 6 }}>
                  {selectedEdge.note}
                </div>
              )}
              {canEditGraph && (
                <button
                  className="btn"
                  style={{ fontSize: 11, padding: "5px 10px", marginTop: 8 }}
                  onClick={() => openDraftEdge(selectedEdge.from, selectedEdge.to)}
                >
                  编辑这条关系
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
