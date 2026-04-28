import { useState } from "react";
import "./index.css";
import { useSimulation } from "./hooks/useSimulation";
import { Header } from "./components/Header";
import { StartPanel } from "./components/StartPanel";
import { WorldPanel } from "./components/WorldPanel";
import { StoryFeed } from "./components/StoryFeed";
import { InterventionPanel } from "./components/InterventionPanel";
import { ExportPanel } from "./components/ExportPanel";
import { RelationshipPanel } from "./components/RelationshipPanel";
import { BranchPanel } from "./components/BranchPanel";

function ErrorBanner({ error }: { error: string | null }) {
  if (!error) return null;
  return (
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
  );
}

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
  const [worldPanelCollapsed, setWorldPanelCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);

  const isRunning = state?.status === "running" || state?.status === "initializing";
  const isWaiting = state?.status === "waiting";
  const isComplete = state?.status === "complete";

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
        <ErrorBanner error={error} />
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

  return (
    <>
      <Header status={state?.status ?? null} onReset={reset} />

      <ErrorBanner error={error} />

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
            {!worldPanelCollapsed && <div className="label">设定集 (Lorebook)</div>}
            <button
              className="btn btn-ghost"
              style={{
                width: worldPanelCollapsed ? "100%" : "auto",
                justifyContent: "center",
                fontSize: 11,
                padding: "6px 8px",
              }}
              aria-label={worldPanelCollapsed ? "展开设定集" : "收起设定集"}
              onClick={() => setWorldPanelCollapsed((value) => !value)}
            >
              {worldPanelCollapsed ? "设定" : "收起"}
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

        {/* Center: Story feed */}
        <main
          className="app-main-panel"
        >
          <div className="app-story-scroll">
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
          </div>
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
            {!rightPanelCollapsed && <div className="label">运行状态 (Status)</div>}
            <button
              className="btn btn-ghost"
              style={{
                width: rightPanelCollapsed ? "100%" : "auto",
                justifyContent: "center",
                fontSize: 11,
                padding: "6px 8px",
              }}
              aria-label={rightPanelCollapsed ? "展开运行状态" : "收起运行状态"}
              onClick={() => setRightPanelCollapsed((value) => !value)}
            >
              {rightPanelCollapsed ? "展开" : "收起"}
            </button>
          </div>

          {!rightPanelCollapsed && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {isComplete && simId && (
                <div style={{ borderBottom: "1px solid var(--color-border)", paddingBottom: 16 }}>
                  <ExportPanel simId={simId} onExport={doExport} />
                </div>
              )}

              {state && (
                <>
                  {state.world && state.features.branching_enabled && (
                    <div style={{ borderBottom: "1px solid var(--color-border)", paddingBottom: 16 }}>
                      <BranchPanel
                        world={state.world}
                        compare={branchCompare}
                        isRunning={isRunning}
                        onSwitch={activateBranch}
                        onPacingChange={setBranchPacing}
                      />
                    </div>
                  )}

                  {isWaiting && state.intervention_context && (
                    <div style={{ borderBottom: "1px solid var(--color-border)", paddingBottom: 16 }}>
                      <InterventionPanel
                        context={state.intervention_context}
                        onSubmit={sendIntervention}
                        onSkip={handleSkip}
                      />
                    </div>
                  )}

                  <RelationshipPanel
                    world={state.world ?? null}
                    simId={simId}
                    isRunning={isRunning}
                    onUpdated={refresh}
                  />
                </>
              )}
            </div>
          )}
        </aside>
      </div>
    </>
  );
}
