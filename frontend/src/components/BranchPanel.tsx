import type { BranchCompareSummary, WorldData } from "../types";
import { useMemo } from "react";

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

// Removed unused pacingLabel

export function BranchPanel({
  world,
  compare,
  isRunning,
  onSwitch,
}: BranchPanelProps) {
  const compareEntries = useMemo(() => {
    return compare ??
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
          } as BranchCompareSummary,
        ])
      );
  }, [compare, world.branches, world.active_branch_id, world.tick]);

  const branchEntries = Object.values(compareEntries);

  // 构建树形结构
  const rootBranches = branchEntries.filter((b) => !b.source_branch_id);
  const getChildren = (branchId: string) => branchEntries.filter((b) => b.source_branch_id === branchId).sort((a, b) => a.created_at_tick - b.created_at_tick);

  const renderBranchNode = (branch: BranchCompareSummary, depth: number) => {
    const children = getChildren(branch.branch_id);
    return (
      <div key={branch.branch_id} style={{ display: "flex", flexDirection: "column" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginLeft: depth * 20,
            padding: "8px 12px",
            background: branch.is_active ? "var(--color-bg-card)" : "transparent",
            border: branch.is_active ? "1px solid var(--color-accent)" : "1px solid transparent",
            borderLeft: branch.is_active ? "3px solid var(--color-accent)" : "3px solid var(--color-border)",
            borderRadius: branch.is_active ? 6 : 0,
            marginBottom: 4,
            cursor: "pointer",
            transition: "all 0.2s ease",
          }}
          onClick={() => {
            if (!branch.is_active && !isRunning) {
              onSwitch(branch.branch_id);
            }
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontWeight: 700, fontSize: 13, color: branch.is_active ? "var(--color-accent)" : "var(--color-text)" }}>
                {branch.label || branch.branch_id}
              </span>
              {branch.is_active && (
                <span className="badge" style={{ borderColor: "var(--color-accent)", color: "var(--color-accent)" }}>当前</span>
              )}
            </div>
            <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginTop: 2, display: "flex", gap: 8 }}>
              <span>节点数: {branch.nodes_count}</span>
              <span>最新: T{branch.latest_tick}</span>
            </div>
          </div>
        </div>
        {children.map((child) => renderBranchNode(child, depth + 1))}
      </div>
    );
  };

  return (
    <div style={{ marginBottom: 16 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div className="label">时间线 (Timelines)</div>
      </div>

      {branchEntries.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          目前只有主线。
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", position: "relative" }}>
          {/* 左侧轨道辅助线 */}
          <div style={{ position: "absolute", left: 1, top: 0, bottom: 0, width: 2, background: "var(--color-border-light)", zIndex: -1 }} />
          {rootBranches.map((branch) => renderBranchNode(branch, 0))}
        </div>
      )}
    </div>
  );
}
