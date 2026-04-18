import type { BranchCompareSummary, WorldData } from "../types";

interface BranchPanelProps {
  world: WorldData;
  compare: Record<string, BranchCompareSummary> | null;
  isRunning: boolean;
  onSwitch: (branchId: string) => void;
  onPacingChange: (
    branchId: string,
    pacing: "calm" | "balanced" | "intense"
  ) => void;
}

const pacingLabel: Record<"calm" | "balanced" | "intense", string> = {
  calm: "平缓",
  balanced: "均衡",
  intense: "高压",
};

export function BranchPanel({
  world,
  compare,
  isRunning,
  onSwitch,
  onPacingChange,
}: BranchPanelProps) {
  const compareEntries =
    compare ??
    Object.fromEntries(
      Object.entries(world.branches).map(([branchId, branch]) => [
        branchId,
        {
          branch_id: branchId,
          label: branch.label,
          forked_from_node: branch.forked_from_node,
          source_branch_id: branch.source_branch_id ?? null,
          source_sim_id: branch.source_sim_id ?? null,
          created_at_tick: branch.created_at_tick ?? 0,
          latest_node_id: branch.latest_node_id ?? null,
          latest_tick: branch.latest_tick ?? world.tick,
          nodes_count: branch.nodes_count ?? 0,
          last_node_summary: branch.last_node_summary ?? null,
          status: branch.status ?? (branchId === world.active_branch_id ? "running" : "complete"),
          pacing: branch.pacing ?? "balanced",
          is_active: branchId === world.active_branch_id,
        } satisfies BranchCompareSummary,
      ])
    );

  const branchEntries = Object.values(compareEntries).sort((left, right) => {
    if (left.is_active) return -1;
    if (right.is_active) return 1;
    return left.created_at_tick - right.created_at_tick;
  });

  return (
    <div className="card" style={{ padding: 16 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div className="label">世界线</div>
        <span style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
          当前：{world.branches[world.active_branch_id]?.label ?? world.active_branch_id}
        </span>
      </div>

      {branchEntries.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          目前只有主线。
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {branchEntries.map((branch) => (
            <div
              key={branch.branch_id}
              className="card card-sm"
              style={{
                borderLeft: branch.is_active
                  ? "3px solid var(--color-warning)"
                  : "3px solid var(--color-border)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                }}
              >
                <div>
                  <div style={{ fontWeight: 700, fontSize: 12 }}>
                    {branch.label}
                  </div>
                  <div
                    style={{
                      fontSize: 10,
                      color: "var(--color-text-muted)",
                      marginTop: 2,
                    }}
                  >
                    {branch.branch_id}
                  </div>
                </div>
                {branch.is_active ? (
                  <span
                    style={{
                      fontSize: 10,
                      padding: "2px 6px",
                      border: "1px solid var(--color-warning)",
                      color: "var(--color-warning)",
                      textTransform: "uppercase",
                    }}
                  >
                    Active
                  </span>
                ) : (
                  <button
                    className="btn"
                    style={{ fontSize: 11, padding: "6px 10px" }}
                    disabled={isRunning}
                    onClick={() => onSwitch(branch.branch_id)}
                  >
                    切换
                  </button>
                )}
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                  gap: 8,
                  marginTop: 10,
                  fontSize: 11,
                  color: "var(--color-text-secondary)",
                }}
              >
                <div>来源节点：{branch.forked_from_node ?? "主线起点"}</div>
                <div>节点数：{branch.nodes_count}</div>
                <div>最新 Tick：T{branch.latest_tick}</div>
                <div>状态：{branch.status}</div>
              </div>

              {branch.last_node_summary && (
                <div
                  style={{
                    marginTop: 8,
                    fontSize: 11,
                    color: "var(--color-text-muted)",
                    lineHeight: 1.5,
                  }}
                >
                  {branch.last_node_summary}
                </div>
              )}

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                  marginTop: 10,
                }}
              >
                <span style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
                  节奏：{pacingLabel[branch.pacing]}
                </span>
                <select
                  value={branch.pacing}
                  disabled={isRunning}
                  onChange={(event) =>
                    onPacingChange(
                      branch.branch_id,
                      event.target.value as "calm" | "balanced" | "intense"
                    )
                  }
                  style={{ fontSize: 11 }}
                >
                  <option value="calm">平缓</option>
                  <option value="balanced">均衡</option>
                  <option value="intense">高压</option>
                </select>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
