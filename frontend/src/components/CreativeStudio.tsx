import {
  lazy,
  Suspense,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import type {
  SimulationDiagnostics,
  SimulationInspector,
  SimulationState,
  WikiCharacterInput,
  WikiEntityInput,
  WikiIssue,
} from "../types";
import { getDiagnostics, getInspector, saveWiki } from "../utils/api";

const RichTextEditor = lazy(() => import("./RichTextEditor"));

interface CreativeStudioProps {
  simId: string;
  state: SimulationState;
  onRefresh: () => void;
}

function createEmptyEntity(): WikiEntityInput {
  return { name: "", description: "", metadata: {} };
}

function createEmptyCharacter(): WikiCharacterInput {
  return {
    id: undefined,
    name: "",
    description: "",
    personality: "",
    goals: [],
    status: "alive",
    metadata: {},
  };
}

export function CreativeStudio({
  simId,
  state,
  onRefresh,
}: CreativeStudioProps) {
  const world = state.world;
  const [activeTab, setActiveTab] = useState<"wiki" | "editor" | "diagnostics">(
    state.nodes.some((node) => Boolean(node.rendered_text)) ? "editor" : "wiki"
  );
  const [title, setTitle] = useState(world?.title ?? "");
  const [premise, setPremise] = useState(world?.premise ?? "");
  const [worldRules, setWorldRules] = useState(world?.world_rules.join("\n") ?? "");
  const [characters, setCharacters] = useState<WikiCharacterInput[]>([]);
  const [factions, setFactions] = useState<WikiEntityInput[]>([]);
  const [locations, setLocations] = useState<WikiEntityInput[]>([]);
  const [issues, setIssues] = useState<WikiIssue[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [diagnostics, setDiagnostics] = useState<SimulationDiagnostics | null>(null);
  const [inspector, setInspector] = useState<SimulationInspector | null>(null);
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);

  useEffect(() => {
    if (!world) return;
    setTitle(world.title);
    setPremise(world.premise);
    setWorldRules(world.world_rules.join("\n"));
    setCharacters(
      world.characters.map((character) => ({
        id: character.id,
        name: character.name,
        description: character.description ?? "",
        personality: character.personality,
        goals: character.goals,
        status: character.status,
        metadata: {},
      }))
    );
    setFactions(
      world.factions.map((entity) => ({
        name: String(entity.name ?? ""),
        description: String(entity.description ?? ""),
        metadata: Object.fromEntries(
          Object.entries(entity).filter(
            ([key]) => key !== "name" && key !== "description"
          )
        ),
      }))
    );
    setLocations(
      world.locations.map((entity) => ({
        name: String(entity.name ?? ""),
        description: String(entity.description ?? ""),
        metadata: Object.fromEntries(
          Object.entries(entity).filter(
            ([key]) => key !== "name" && key !== "description"
          )
        ),
      }))
    );
  }, [world]);

  useEffect(() => {
    if (activeTab !== "diagnostics") return;
    let cancelled = false;
    setDiagnosticsError(null);
    void Promise.all([getDiagnostics(simId), getInspector(simId)])
      .then(([nextDiagnostics, nextInspector]) => {
        if (!cancelled) {
          setDiagnostics(nextDiagnostics);
          setInspector(nextInspector);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setDiagnosticsError(String(error));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeTab, simId]);

  if (!world) {
    return null;
  }

  const updateCharacterField = (
    index: number,
    key: keyof WikiCharacterInput,
    value: string | string[]
  ) => {
    setCharacters((prev) =>
      prev.map((character, currentIndex) =>
        currentIndex === index ? { ...character, [key]: value } : character
      )
    );
  };

  const updateEntityField = (
    setter: Dispatch<SetStateAction<WikiEntityInput[]>>,
    index: number,
    key: keyof WikiEntityInput,
    value: string
  ) => {
    setter((prev) =>
      prev.map((entity, currentIndex) =>
        currentIndex === index ? { ...entity, [key]: value } : entity
      )
    );
  };

  const handleSaveWiki = async () => {
    setSaving(true);
    setStatus(null);
    setIssues([]);
    try {
      const response = await saveWiki(simId, {
        title,
        premise,
        world_rules: worldRules
          .split("\n")
          .map((rule) => rule.trim())
          .filter(Boolean),
        factions,
        locations,
        characters: characters.map((character) => ({
          ...character,
          goals: character.goals.filter(Boolean),
        })),
      });
      setIssues(response.issues);
      setStatus(response.message);
      onRefresh();
    } catch (error) {
      setStatus(String(error));
    } finally {
      setSaving(false);
    }
  };

  const tabButton = (
    key: "wiki" | "editor" | "diagnostics",
    label: string
  ) => (
    <button
      key={key}
      type="button"
      className={`btn ${activeTab === key ? "btn-primary" : ""}`}
      onClick={() => setActiveTab(key)}
    >
      {label}
    </button>
  );

  const sharedInputStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 12px",
    border: "1px solid var(--color-border)",
    background: "var(--color-bg-card)",
    fontSize: 13,
    fontFamily: "inherit",
  };

  return (
    <section
      className="card"
      style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 16 }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div className="label">Sprint 9 Studio</div>
          <div className="heading">创作工作台</div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {tabButton("wiki", "Wiki")}
          {tabButton("editor", "富文本")}
          {tabButton("diagnostics", "诊断")}
        </div>
      </div>

      {status && (
        <div
          style={{
            padding: "10px 12px",
            border: "1px solid var(--color-border)",
            background: "var(--color-bg)",
            fontSize: 12,
          }}
        >
          {status}
        </div>
      )}

      {activeTab === "wiki" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <div className="label" style={{ marginBottom: 6 }}>
                标题
              </div>
              <input
                style={sharedInputStyle}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </div>
            <div>
              <div className="label" style={{ marginBottom: 6 }}>
                前提
              </div>
              <input
                style={sharedInputStyle}
                value={premise}
                onChange={(event) => setPremise(event.target.value)}
              />
            </div>
          </div>

          <div>
            <div className="label" style={{ marginBottom: 6 }}>
              世界规则
            </div>
            <textarea
              style={{ ...sharedInputStyle, minHeight: 120 }}
              value={worldRules}
              onChange={(event) => setWorldRules(event.target.value)}
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div
                style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
              >
                <div className="label">角色</div>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setCharacters((prev) => [...prev, createEmptyCharacter()])}
                >
                  新增角色
                </button>
              </div>
              {characters.map((character, index) => (
                <div
                  key={character.id ?? `new-character-${index}`}
                  style={{
                    border: "1px solid var(--color-border-light)",
                    padding: 12,
                    background: "var(--color-bg)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                  }}
                >
                  <input
                    style={sharedInputStyle}
                    placeholder="角色名"
                    value={character.name}
                    onChange={(event) =>
                      updateCharacterField(index, "name", event.target.value)
                    }
                  />
                  <input
                    style={sharedInputStyle}
                    placeholder="角色描述"
                    value={character.description}
                    onChange={(event) =>
                      updateCharacterField(index, "description", event.target.value)
                    }
                  />
                  <input
                    style={sharedInputStyle}
                    placeholder="性格"
                    value={character.personality}
                    onChange={(event) =>
                      updateCharacterField(index, "personality", event.target.value)
                    }
                  />
                  <textarea
                    style={{ ...sharedInputStyle, minHeight: 72 }}
                    placeholder="目标（每行一条）"
                    value={character.goals.join("\n")}
                    onChange={(event) =>
                      updateCharacterField(
                        index,
                        "goals",
                        event.target.value
                          .split("\n")
                          .map((goal) => goal.trim())
                          .filter(Boolean)
                      )
                    }
                  />
                </div>
              ))}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {[
                {
                  label: "势力",
                  items: factions,
                  setter: setFactions,
                },
                {
                  label: "地点",
                  items: locations,
                  setter: setLocations,
                },
              ].map(({ label, items, setter }) => (
                <div key={label} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div className="label">{label}</div>
                    <button
                      type="button"
                      className="btn"
                      onClick={() => setter((prev) => [...prev, createEmptyEntity()])}
                    >
                      新增{label}
                    </button>
                  </div>
                  {items.map((entity, index) => (
                    <div
                      key={`${label}-${index}`}
                      style={{
                        border: "1px solid var(--color-border-light)",
                        padding: 12,
                        background: "var(--color-bg)",
                        display: "flex",
                        flexDirection: "column",
                        gap: 8,
                      }}
                    >
                      <input
                        style={sharedInputStyle}
                        placeholder={`${label}名`}
                        value={entity.name}
                        onChange={(event) =>
                          updateEntityField(setter, index, "name", event.target.value)
                        }
                      />
                      <textarea
                        style={{ ...sharedInputStyle, minHeight: 72 }}
                        placeholder="说明"
                        value={entity.description}
                        onChange={(event) =>
                          updateEntityField(
                            setter,
                            index,
                            "description",
                            event.target.value
                          )
                        }
                      />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>

          {issues.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {issues.map((issue, index) => (
                <div
                  key={`${issue.path}-${index}`}
                  style={{
                    padding: "8px 10px",
                    border: "1px solid var(--color-border)",
                    background:
                      issue.level === "error"
                        ? "rgba(192, 57, 43, 0.08)"
                        : "rgba(230, 126, 34, 0.08)",
                    color:
                      issue.level === "error"
                        ? "var(--color-danger)"
                        : "var(--color-warning)",
                    fontSize: 12,
                  }}
                >
                  {issue.path}: {issue.message}
                </div>
              ))}
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={saving}
              onClick={handleSaveWiki}
            >
              {saving ? "保存中..." : "保存 Wiki"}
            </button>
          </div>
        </div>
      )}

      {activeTab === "editor" && (
        <Suspense fallback={<div style={{ fontSize: 12 }}>正在加载编辑器...</div>}>
          <RichTextEditor
            simId={simId}
            activeBranchId={world.active_branch_id}
            nodes={state.nodes}
            onSaved={onRefresh}
          />
        </Suspense>
      )}

      {activeTab === "diagnostics" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {diagnosticsError && (
            <div style={{ fontSize: 12, color: "var(--color-danger)" }}>
              {diagnosticsError}
            </div>
          )}
          {diagnostics && (
            <>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                  gap: 12,
                }}
              >
                {[
                  ["活跃记忆", diagnostics.memory.active_entries],
                  ["归档摘要", diagnostics.memory.summary_entries],
                  ["反思记忆", diagnostics.memory.reflection_entries],
                  ["LLM 调用", diagnostics.llm.total_calls],
                  ["提示词估算", diagnostics.llm.estimated_prompt_tokens],
                  ["向量后端", diagnostics.memory.vector_backend ?? "simple"],
                  [
                    "双循环开关",
                    diagnostics.dual_loop.enabled ? "enabled" : "disabled",
                  ],
                  ["契约版本", diagnostics.dual_loop.contract_version],
                  ["适配模式", diagnostics.dual_loop.adapter_mode],
                ].map(([label, value]) => (
                  <div
                    key={String(label)}
                    style={{
                      border: "1px solid var(--color-border)",
                      background: "var(--color-bg)",
                      padding: 12,
                    }}
                  >
                    <div className="label" style={{ marginBottom: 6 }}>
                      {label}
                    </div>
                    <div className="heading">{value}</div>
                  </div>
                ))}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div className="label">路由分布</div>
                {diagnostics.llm.routes.map((route) => (
                  <div
                    key={`${route.route_group}-${route.provider}-${route.model}`}
                    style={{
                      border: "1px solid var(--color-border-light)",
                      padding: 12,
                      background: "var(--color-bg)",
                    }}
                  >
                    <div style={{ fontSize: 12, fontWeight: 600 }}>
                      {route.route_group} · {route.provider} / {route.model}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                      calls={route.calls} · duration={route.duration_ms}ms · fallback=
                      {route.fallbacks}
                    </div>
                  </div>
                ))}
              </div>

              {inspector && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div className="label">Prompt Inspector</div>
                  <div
                    style={{
                      border: "1px solid var(--color-border-light)",
                      padding: 12,
                      background: "var(--color-bg)",
                      display: "grid",
                      gap: 8,
                    }}
                  >
                    <div style={{ fontSize: 12, fontWeight: 600 }}>
                      {inspector.node_title ?? inspector.scene_plan.title}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                      prompts={inspector.summary.prompt_trace_count} · intents=
                      {inspector.summary.action_intent_count} · critic rejected=
                      {inspector.summary.critic_rejected_count}
                    </div>
                    {inspector.prompt_traces.slice(0, 2).map((trace) => (
                      <div
                        key={trace.trace_id}
                        style={{
                          borderTop: "1px solid var(--color-border-light)",
                          paddingTop: 8,
                          fontSize: 12,
                        }}
                      >
                        <div style={{ fontWeight: 600 }}>
                          {trace.agent} · {trace.character_id ?? "world"}
                        </div>
                        <div style={{ color: "var(--color-text-muted)" }}>
                          pressure={trace.narrative_pressure} · visible=
                          {trace.visible_character_ids.length} · working=
                          {trace.memory_trace?.working_memory.length ?? 0} · episodic=
                          {trace.memory_trace?.episodic_memory_snippets.length ?? 0} ·
                          reflective={trace.memory_trace?.reflective_memory.length ?? 0}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div className="label">Dual-Loop Snapshot</div>
                <div
                  style={{
                    border: "1px solid var(--color-border-light)",
                    padding: 12,
                    background: "var(--color-bg)",
                    display: "grid",
                    gap: 8,
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 600 }}>
                    {diagnostics.dual_loop.scene_plan?.title ?? "尚未生成 ScenePlan"}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                    pressure=
                    {diagnostics.dual_loop.scene_plan?.narrative_pressure ?? "balanced"} ·
                    spotlight=
                    {diagnostics.dual_loop.scene_plan?.spotlight_character_ids.length ?? 0} ·
                    intents={diagnostics.dual_loop.action_intents.length} · critic=
                    {
                      diagnostics.dual_loop.intent_critiques.filter(
                        (critique) => critique.accepted
                      ).length
                    }
                    /
                    {
                      diagnostics.dual_loop.intent_critiques.filter(
                        (critique) => !critique.accepted
                      ).length
                    }{" "}
                    · script=
                    {diagnostics.dual_loop.scene_script?.accepted_intent_ids.length ?? 0}
                    /
                    {diagnostics.dual_loop.scene_script?.rejected_intent_ids.length ?? 0}
                  </div>
                  {diagnostics.dual_loop.scene_script?.summary && (
                    <div style={{ fontSize: 12 }}>
                      {diagnostics.dual_loop.scene_script.summary}
                    </div>
                  )}
                  {diagnostics.dual_loop.intent_critiques.some(
                    (critique) => !critique.accepted
                  ) && (
                    <div
                      style={{
                        display: "grid",
                        gap: 6,
                        fontSize: 12,
                        color: "var(--color-warning)",
                      }}
                    >
                      {diagnostics.dual_loop.intent_critiques
                        .filter((critique) => !critique.accepted)
                        .map((critique) => (
                          <div key={critique.critique_id}>
                            {critique.actor_name || critique.actor_id}:{" "}
                            {critique.reason_code}
                            {critique.reason ? ` · ${critique.reason}` : ""}
                          </div>
                        ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
