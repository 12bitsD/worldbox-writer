import { useState } from "react";
import "./index.css";
import { useSimulation } from "./hooks/useSimulation";
import { Header } from "./components/Header";
import { StartPanel } from "./components/StartPanel";
import { WorldPanel } from "./components/WorldPanel";
import { StoryFeed } from "./components/StoryFeed";
import { InterventionPanel } from "./components/InterventionPanel";
import { ExportPanel } from "./components/ExportPanel";
import { EditPanel } from "./components/EditPanel";
import { RelationshipPanel } from "./components/RelationshipPanel";
import { TelemetryPanel } from "./components/TelemetryPanel";
import { BranchPanel } from "./components/BranchPanel";
import { ProgressPanel } from "./components/ProgressPanel";
import { CreativeStudio } from "./components/CreativeStudio";

export default function App() {
  const {
    simId,
    state,
    branchCompare,
    loading,
    error,
    recentSessions,
    start,
    openSession,
    sendIntervention,
    forkAtNode,
    activateBranch,
    setBranchPacing,
    doExport,
    refresh,
    reset,
  } =
    useSimulation();
  const [rightTab, setRightTab] = useState<"graph" | "telemetry">("graph");
  const [worldPanelCollapsed, setWorldPanelCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);

  const isRunning = state?.status === "running" || state?.status === "initializing";
  const isWaiting = state?.status === "waiting";
  const isComplete = state?.status === "complete";
  const showProgressPanel = Boolean(
    state &&
      (state.status === "initializing" || state.status === "running") &&
      !state.nodes.some((node) => Boolean(node.rendered_text)) &&
      (state.telemetry.length > 0 || state.nodes.length === 0)
  );

  const handleSkip = () => {
    sendIntervention("按照故事自然发展，不干预");
  };

  const handleForkNode = (nodeId: string) => {
    const label = window.prompt("新分支名称（可留空使用默认命名）")?.trim();
    void forkAtNode(nodeId, {
      label: label || undefined,
      continueSimulation: true,
    });
  };

  // No simulation started yet
  if (!simId && !loading) {
    return (
      <>
        <Header status={null} onReset={reset} />
        <StartPanel
          onStart={start}
          onOpenSession={openSession}
          recentSessions={recentSessions}
          loading={loading}
        />
      </>
    );
  }

  // Loading / initializing
  if (loading && !state) {
    return (
      <>
        <Header status="initializing" onReset={reset} />
        <div
          style={{
            minHeight: "calc(100vh - 52px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexDirection: "column",
            gap: 16,
          }}
        >
          <span
            className="animate-pulse-dot"
            style={{
              width: 12,
              height: 12,
              borderRadius: "50%",
              background: "var(--color-text)",
              display: "inline-block",
            }}
          />
          <p style={{ color: "var(--color-text-muted)", fontSize: 13 }}>
            Director Agent 正在初始化世界...
          </p>
        </div>
      </>
    );
  }

  const agentList = [
    { name: "Director", active: isRunning },
    { name: "WorldBuilder", active: isRunning && (state?.nodes.length ?? 0) === 0 },
    { name: "Actor × N", active: isRunning },
    { name: "GateKeeper", active: isRunning },
    { name: "NodeDetector", active: isRunning },
    { name: "Narrator", active: isRunning },
  ];

  const nodeTypeLegend = [
    { type: "setup", label: "序章", color: "#6b7280" },
    { type: "development", label: "发展", color: "#374151" },
    { type: "branch", label: "分支", color: "#d97706" },
    { type: "climax", label: "高潮", color: "#dc2626" },
    { type: "resolution", label: "结局", color: "#059669" },
  ];

  return (
    <>
      <Header status={state?.status ?? null} onReset={reset} />

      {error && (
        <div
          style={{
            padding: "10px 32px",
            background: "rgba(192, 57, 43, 0.08)",
            borderBottom: "1px solid rgba(192, 57, 43, 0.3)",
            fontSize: 12,
            color: "var(--color-danger)",
          }}
        >
          错误：{error}
        </div>
      )}

      {/* Main 3-column layout */}
      <div
        className="app-shell"
        style={{
          gridTemplateColumns: rightPanelCollapsed
            ? `${worldPanelCollapsed ? "56px" : "280px"} minmax(0, 1fr) 56px`
            : `${worldPanelCollapsed ? "56px" : "280px"} minmax(0, 1fr) 320px`,
        }}
      >
        {/* Left: World state panel */}
        <aside
          className="app-side-panel app-side-panel-left"
          style={{ padding: worldPanelCollapsed ? 12 : 20 }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 8,
              marginBottom: worldPanelCollapsed ? 0 : 16,
            }}
          >
            {!worldPanelCollapsed && <div className="label">世界面板</div>}
            <button
              className="btn btn-ghost"
              style={{
                width: worldPanelCollapsed ? "100%" : "auto",
                justifyContent: "center",
                fontSize: 11,
                padding: "6px 8px",
              }}
              aria-label={worldPanelCollapsed ? "展开世界面板" : "收起世界面板"}
              onClick={() => setWorldPanelCollapsed((value) => !value)}
            >
              {worldPanelCollapsed ? "世界" : "收起"}
            </button>
          </div>

          {!worldPanelCollapsed && (
            state?.world ? (
              <WorldPanel world={state.world} />
            ) : (
              <div>
                <div style={{ color: "var(--color-text-muted)", fontSize: 12 }}>
                  世界正在初始化...
                </div>
              </div>
            )
          )}
        </aside>

        {/* Center: Story feed + intervention */}
        <main
          className="app-main-panel"
        >
          <div className="app-story-scroll">
            {state && (
              <>
                {showProgressPanel && (
                  <ProgressPanel
                    events={state.telemetry}
                    isRunning={isRunning}
                  />
                )}
              </>
            )}
            {state && (
              <StoryFeed
                nodes={state.nodes}
                isRunning={isRunning}
                branchingEnabled={state.features.branching_enabled}
                activeBranchId={state.world?.active_branch_id ?? "main"}
                onForkNode={handleForkNode}
                simId={simId}
                world={state.world}
                telemetryEvents={state.telemetry}
                onWorldUpdated={refresh}
              />
            )}
            {isComplete && simId && (
              <div style={{ marginTop: 16 }}>
                <ExportPanel simId={simId} onExport={doExport} />
              </div>
            )}
            {!isRunning && simId && state?.world && (
              <CreativeStudio
                simId={simId}
                state={state}
                onRefresh={refresh}
              />
            )}
          </div>

          {isWaiting && state?.intervention_context && (
            <InterventionPanel
              context={state.intervention_context}
              onSubmit={sendIntervention}
              onSkip={handleSkip}
              editPanel={
                simId && state.world ? (
                  <EditPanel
                    simId={simId}
                    world={state.world}
                    onUpdated={refresh}
                    embedded
                  />
                ) : undefined
              }
            />
          )}
        </main>

        {/* Right: Meta info panel */}
        <aside
          className="app-side-panel app-side-panel-right"
          style={{ padding: rightPanelCollapsed ? 12 : 20 }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 8,
              marginBottom: rightPanelCollapsed ? 0 : 16,
            }}
          >
            {!rightPanelCollapsed && <div className="label">推演信息</div>}
            <button
              className="btn btn-ghost"
              style={{
                width: rightPanelCollapsed ? "100%" : "auto",
                justifyContent: "center",
                fontSize: 11,
                padding: "6px 8px",
              }}
              aria-label={rightPanelCollapsed ? "展开推演信息" : "收起推演信息"}
              onClick={() => setRightPanelCollapsed((value) => !value)}
            >
              {rightPanelCollapsed ? "展开" : "收起"}
            </button>
          </div>

          {!rightPanelCollapsed && (
            <>
          {simId && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginBottom: 4 }}>
                推演 ID
              </div>
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: 12,
                  padding: "4px 8px",
                  background: "var(--color-bg)",
                  border: "1px solid var(--color-border)",
                }}
              >
                {simId}
              </div>
            </div>
          )}

          {state && (
            <>
              {state.world && state.features.branching_enabled && (
                <div style={{ marginBottom: 16 }}>
                  <BranchPanel
                    world={state.world}
                    compare={branchCompare}
                    isRunning={isRunning}
                    onSwitch={activateBranch}
                    onPacingChange={setBranchPacing}
                  />
                </div>
              )}
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginBottom: 4 }}>
                  故事节点
                </div>
                <div style={{ fontSize: 24, fontWeight: 800 }}>{state.nodes.length}</div>
              </div>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginBottom: 4 }}>
                  干预次数
                </div>
                <div style={{ fontSize: 24, fontWeight: 800 }}>
                  {state.nodes.filter((n) => n.requires_intervention).length}
                </div>
              </div>
              {state.world && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginBottom: 4 }}>
                    当前时间轴
                  </div>
                  <div style={{ fontSize: 24, fontWeight: 800 }}>T{state.world.tick}</div>
                </div>
              )}
            </>
          )}

          <hr style={{ border: "none", borderTop: "1px solid var(--color-border)", margin: "16px 0" }} />

          <div className="label" style={{ marginBottom: 10 }}>
            节点类型
          </div>
          {nodeTypeLegend.map((item) => (
            <div
              key={item.type}
              style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, fontSize: 12 }}
            >
              <span
                style={{
                  width: 12,
                  height: 12,
                  background: item.color,
                  display: "inline-block",
                  flexShrink: 0,
                }}
              />
              <span style={{ color: "var(--color-text-secondary)" }}>{item.label}</span>
            </div>
          ))}

          <hr style={{ border: "none", borderTop: "1px solid var(--color-border)", margin: "16px 0" }} />

          <div className="label" style={{ marginBottom: 10 }}>
            Agent 状态
          </div>
          {agentList.map((agent) => (
            <div
              key={agent.name}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 6,
                fontSize: 12,
              }}
            >
              <span style={{ color: "var(--color-text-secondary)" }}>{agent.name}</span>
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: agent.active ? "var(--color-success)" : "var(--color-border)",
                  display: "inline-block",
                }}
                className={agent.active ? "animate-pulse-dot" : ""}
              />
            </div>
          ))}

          <hr style={{ border: "none", borderTop: "1px solid var(--color-border)", margin: "16px 0" }} />

          <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
            <button
              className={`btn ${rightTab === "graph" ? "btn-primary" : ""}`}
              style={{ flex: 1, justifyContent: "center", fontSize: 11, padding: "6px 10px" }}
              onClick={() => setRightTab("graph")}
            >
              Graph
            </button>
            <button
              className={`btn ${rightTab === "telemetry" ? "btn-primary" : ""}`}
              style={{ flex: 1, justifyContent: "center", fontSize: 11, padding: "6px 10px" }}
              onClick={() => setRightTab("telemetry")}
            >
              Telemetry
            </button>
          </div>

          {rightTab === "graph" ? (
            <RelationshipPanel
              world={state?.world ?? null}
              simId={simId}
              isRunning={isRunning}
              onUpdated={refresh}
            />
          ) : (
            <TelemetryPanel
              events={state?.telemetry ?? []}
              isRunning={isRunning}
            />
          )}
            </>
          )}
        </aside>
      </div>
    </>
  );
}
