import type { StoryNode, NodeType } from "../types";

interface StoryFeedProps {
  nodes: StoryNode[];
  isRunning: boolean;
}

const nodeTypeLabel: Record<NodeType, string> = {
  setup: "序章",
  development: "发展",
  branch: "分支",
  climax: "高潮",
  resolution: "结局",
};

export function StoryFeed({ nodes, isRunning }: StoryFeedProps) {
  if (nodes.length === 0 && !isRunning) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      <div className="label" style={{ marginBottom: 16 }}>
        故事推演
      </div>

      {nodes.map((node) => (
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
              }}
            >
              {nodeTypeLabel[node.node_type] || node.node_type}
            </span>
            <span style={{ fontWeight: 700, fontSize: 13 }}>{node.title}</span>
            {node.requires_intervention && (
              <span
                style={{
                  marginLeft: "auto",
                  fontSize: 10,
                  padding: "1px 6px",
                  border: "1px solid var(--color-warning)",
                  color: "var(--color-warning)",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                已干预
              </span>
            )}
          </div>

          {/* Node body */}
          <div style={{ padding: "12px 16px" }}>
            {/* Description */}
            <p
              style={{
                fontSize: 12,
                color: "var(--color-text-secondary)",
                marginBottom: node.rendered_text ? 12 : 0,
                lineHeight: 1.6,
              }}
            >
              {node.description}
            </p>

            {/* Rendered novel text */}
            {node.rendered_text && (
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
                {node.rendered_text}
              </div>
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
      ))}

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
