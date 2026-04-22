import type { StoryNode, NodeType } from "../types";

interface StoryFeedProps {
  nodes: StoryNode[];
  isRunning: boolean;
  branchingEnabled: boolean;
  activeBranchId: string;
  onForkNode: (nodeId: string) => void;
}

const nodeTypeLabel: Record<NodeType, string> = {
  setup: "序章",
  development: "发展",
  branch: "分支",
  climax: "高潮",
  resolution: "结局",
};

export function StoryFeed({
  nodes,
  isRunning,
  branchingEnabled,
  activeBranchId,
  onForkNode,
}: StoryFeedProps) {
  if (nodes.length === 0 && !isRunning) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      <div className="label" style={{ marginBottom: 16 }}>
        故事推演
      </div>

      {nodes.map((node) => {
        const narrativeText = node.rendered_text || node.streaming_text;

        return (
          <div
            key={node.id}
            className={`animate-fade-in node-${node.node_type}`}
            style={{
              marginBottom: 16,
              background: "var(--color-bg-card)",
              border: "1px solid var(--color-border)",
              overflow: "hidden",
            }}
          >
            {/* Node header */}
            <div
              style={{
                padding: "10px 16px",
                borderBottom: "1px solid var(--color-border-light)",
                display: "flex",
                alignItems: "center",
                gap: 12,
              }}
            >
              <div
                style={{
                  minWidth: 0,
                  flex: 1,
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                }}
              >
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: "var(--color-text-muted)",
                    minWidth: 28,
                  }}
                >
                  T{node.tick}
                </span>
                <span
                  style={{
                    fontSize: 10,
                    padding: "1px 6px",
                    border: "1px solid var(--color-border)",
                    color: "var(--color-text-muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    flexShrink: 0,
                  }}
                >
                  {nodeTypeLabel[node.node_type] || node.node_type}
                </span>
                <span
                  style={{
                    fontWeight: 700,
                    fontSize: 13,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {node.title}
                </span>
                <span
                  style={{
                    fontSize: 10,
                    padding: "1px 6px",
                    border: "1px solid var(--color-border)",
                    color:
                      node.branch_id === activeBranchId
                        ? "var(--color-warning)"
                        : "var(--color-text-muted)",
                    flexShrink: 0,
                  }}
                >
                  {node.branch_id}
                </span>
              </div>

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  flexShrink: 0,
                }}
              >
                {node.requires_intervention && (
                  <span
                    style={{
                      fontSize: 10,
                      padding: "1px 6px",
                      border: "1px solid var(--color-warning)",
                      color: "var(--color-warning)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                    }}
                  >
                    {node.intervention_instruction ? "已干预" : "关键节点"}
                  </span>
                )}
                {branchingEnabled && !isRunning && (
                  <button
                    className="btn"
                    style={{ fontSize: 11, padding: "6px 10px" }}
                    onClick={() => onForkNode(node.id)}
                  >
                    从此分叉
                  </button>
                )}
              </div>
            </div>

            {/* Node body */}
            <div style={{ padding: "12px 16px" }}>
              {narrativeText ? (
                <div
                  style={{
                    padding: "12px 16px",
                    background: "var(--color-bg)",
                    borderLeft: "2px solid var(--color-border)",
                    fontSize: 13,
                    lineHeight: 1.8,
                    color: "var(--color-text)",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {narrativeText}
                  {!node.rendered_text && node.streaming_text && (
                    <span className="typing-cursor" style={{ marginLeft: 2 }}>
                      |
                    </span>
                  )}
                </div>
              ) : (
                <p
                  style={{
                    fontSize: 12,
                    color: "var(--color-text-secondary)",
                    marginBottom: node.scene_script_summary ? 12 : 0,
                    lineHeight: 1.6,
                  }}
                >
                  {node.description}
                </p>
              )}

              {narrativeText && node.description && (
                <details
                  style={{
                    marginTop: 10,
                    border: "1px solid var(--color-border-light)",
                    background: "rgba(17, 17, 17, 0.02)",
                    fontSize: 11,
                    color: "var(--color-text-secondary)",
                  }}
                >
                  <summary
                    style={{
                      cursor: "pointer",
                      padding: "6px 10px",
                      fontWeight: 700,
                      color: "var(--color-text-muted)",
                    }}
                  >
                    逻辑摘要
                  </summary>
                  <p style={{ padding: "0 10px 8px", lineHeight: 1.5 }}>
                    {node.description}
                  </p>
                </details>
              )}

              {node.scene_script_summary && (
                <details
                  style={{
                    marginTop: 10,
                    border: "1px solid rgba(28, 128, 98, 0.16)",
                    background: "rgba(28, 128, 98, 0.06)",
                    fontSize: 11,
                    lineHeight: 1.5,
                    color: "var(--color-text-secondary)",
                  }}
                >
                  <summary
                    style={{
                      cursor: "pointer",
                      padding: "6px 10px",
                      fontWeight: 700,
                      color: "var(--color-text)",
                    }}
                  >
                    SceneScript
                  </summary>
                  <div style={{ padding: "0 10px 8px" }}>
                    {node.scene_script_summary}
                  </div>
                </details>
              )}

              {/* Intervention instruction */}
              {node.intervention_instruction && (
                <div
                  style={{
                    marginTop: 10,
                    padding: "8px 12px",
                    background: "rgba(230, 126, 34, 0.06)",
                    border: "1px solid rgba(230, 126, 34, 0.2)",
                    fontSize: 11,
                    color: "var(--color-warning)",
                  }}
                >
                  <span style={{ fontWeight: 600 }}>干预指令：</span>
                  {node.intervention_instruction}
                </div>
              )}
            </div>
          </div>
        );
      })}

      {/* Running indicator */}
      {isRunning && (
        <div
          style={{
            padding: "16px",
            border: "1px solid var(--color-border)",
            display: "flex",
            alignItems: "center",
            gap: 10,
            color: "var(--color-text-muted)",
            fontSize: 12,
          }}
        >
          <span
            className="animate-pulse-dot"
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "var(--color-success)",
              display: "inline-block",
            }}
          />
          Agent 集群正在推演下一个故事节点...
        </div>
      )}
    </div>
  );
}
