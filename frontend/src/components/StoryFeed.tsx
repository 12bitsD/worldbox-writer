import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type {
  Character,
  NodeType,
  StoryNode,
  TelemetryEvent,
  WorldData,
} from "../types";
import { updateCharacter } from "../utils/api";

interface StoryFeedProps {
  nodes: StoryNode[];
  isRunning: boolean;
  branchingEnabled: boolean;
  activeBranchId: string;
  onForkNode: (nodeId: string) => void;
  simId?: string | null;
  world?: WorldData | null;
  telemetryEvents?: TelemetryEvent[];
  onWorldUpdated?: () => void;
}

type AnchorSource = "console" | "reader";

const nodeTypeLabel: Record<NodeType, string> = {
  setup: "序章",
  development: "发展",
  branch: "分支",
  climax: "高潮",
  resolution: "结局",
};

const statusColor: Record<TelemetryEvent["level"], string> = {
  info: "var(--color-success)",
  warning: "var(--color-warning)",
  error: "var(--color-danger)",
};

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buildStatusLabel(event: TelemetryEvent): string {
  const agent = event.agent || "system";
  const message = event.message || event.stage;
  if (event.stage.includes("retry")) return `自动重试：${message}`;
  if (event.stage.includes("critique")) return `质检员审查：${message}`;
  if (event.stage.includes("gate") || event.agent === "gate_keeper") {
    return `规则引擎校验：${message}`;
  }
  if (event.level === "error") return `${agent}：${message}`;
  if (event.stage.includes("intent") || event.stage.includes("proposal")) {
    return `${agent} 意图生成完毕`;
  }
  if (event.duration_ms == null && event.span_kind === "llm") {
    return `${agent} 思考中...`;
  }
  return `${agent}：${message}`;
}

function buildConsoleLines(node: StoryNode): Array<{
  role: string;
  body: string;
  tone: "director" | "actor" | "gm" | "user";
}> {
  const lines: Array<{
    role: string;
    body: string;
    tone: "director" | "actor" | "gm" | "user";
  }> = [
    {
      role: "导演",
      body: `发起场景：${node.title}`,
      tone: "director",
    },
  ];

  if (node.description) {
    lines.push({
      role: "内循环",
      body: node.description,
      tone: "actor",
    });
  }

  if (node.scene_script_summary) {
    lines.push({
      role: "SceneScript",
      body: node.scene_script_summary,
      tone: "gm",
    });
  }

  if (node.intervention_instruction) {
    lines.push({
      role: "用户干预",
      body: node.intervention_instruction,
      tone: "user",
    });
  }

  return lines;
}

function EntityMention({
  active,
  character,
  disabled,
  mentionKey,
  onOpen,
  onWorldUpdated,
  simId,
}: {
  active: boolean;
  character: Character;
  disabled: boolean;
  mentionKey: string;
  onOpen: (key: string) => void;
  onWorldUpdated?: () => void;
  simId?: string | null;
}) {
  const [personality, setPersonality] = useState(character.personality);
  const [goals, setGoals] = useState(character.goals.join("\n"));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;
    setPersonality(character.personality);
    setGoals(character.goals.join("\n"));
    setError(null);
  }, [active, character.goals, character.personality]);

  const handleSave = async () => {
    if (!simId) return;
    setSaving(true);
    setError(null);
    try {
      await updateCharacter(simId, character.id, {
        personality,
        goals: goals.split("\n").map((goal) => goal.trim()).filter(Boolean),
      });
      await onWorldUpdated?.();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <span className="entity-mention-wrap">
      <button
        type="button"
        className="entity-mention"
        onClick={(event) => {
          event.stopPropagation();
          onOpen(mentionKey);
        }}
      >
        {character.name}
      </button>
      {active && (
        <span
          className="entity-card"
          role="dialog"
          aria-label={`${character.name} 设定卡`}
          onClick={(event) => event.stopPropagation()}
        >
          <span className="entity-card-title">{character.name}</span>
          <span className="entity-card-muted">状态：{character.status}</span>
          {character.description && (
            <span className="entity-card-text">{character.description}</span>
          )}
          <label className="entity-card-field">
            Prompt 性格
            <textarea
              className="input textarea"
              value={personality}
              onChange={(event) => setPersonality(event.target.value)}
              disabled={disabled || saving}
            />
          </label>
          <label className="entity-card-field">
            目标 / 动机（每行一个）
            <textarea
              className="input textarea"
              value={goals}
              onChange={(event) => setGoals(event.target.value)}
              disabled={disabled || saving}
            />
          </label>
          {character.memory.length > 0 && (
            <span className="entity-card-memory">
              最近记忆：{character.memory.slice(-2).join(" / ")}
            </span>
          )}
          {disabled && (
            <span className="entity-card-muted">
              运行中不可直接改设定，请等关键节点暂停或推演完成。
            </span>
          )}
          {error && <span className="entity-card-error">{error}</span>}
          <button
            type="button"
            className="btn btn-primary"
            disabled={disabled || saving}
            onClick={handleSave}
          >
            {saving ? "保存中..." : "保存设定"}
          </button>
        </span>
      )}
    </span>
  );
}

export function StoryFeed({
  nodes,
  isRunning,
  branchingEnabled,
  activeBranchId,
  onForkNode,
  simId,
  world,
  telemetryEvents = [],
  onWorldUpdated,
}: StoryFeedProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [activeMentionKey, setActiveMentionKey] = useState<string | null>(null);
  const consoleRefs = useRef(new Map<string, HTMLDivElement>());
  const readerRefs = useRef(new Map<string, HTMLElement>());
  const readerPaneRef = useRef<HTMLDivElement | null>(null);
  const consolePaneRef = useRef<HTMLDivElement | null>(null);

  const characters = useMemo(
    () =>
      [...(world?.characters ?? [])]
        .filter((character) => character.name.trim().length > 0)
        .sort((left, right) => right.name.length - left.name.length),
    [world?.characters]
  );

  const characterPattern = useMemo(() => {
    if (characters.length === 0) return null;
    return new RegExp(`(${characters.map((character) => escapeRegExp(character.name)).join("|")})`, "g");
  }, [characters]);

  const latestStatusChips = useMemo(
    () => [...telemetryEvents].slice(-6).reverse(),
    [telemetryEvents]
  );

  const activeNodeId = nodes.some((node) => node.id === selectedNodeId)
    ? selectedNodeId
    : nodes.at(-1)?.id ?? null;

  useEffect(() => {
    const root = readerPaneRef.current;
    if (!root || typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        const nextNodeId = visible?.target.getAttribute("data-node-id");
        if (!nextNodeId) return;
        setSelectedNodeId(nextNodeId);
        consoleRefs.current.get(nextNodeId)?.scrollIntoView({
          block: "nearest",
          behavior: "smooth",
        });
      },
      { root, threshold: [0.45, 0.7] }
    );

    for (const element of readerRefs.current.values()) {
      observer.observe(element);
    }

    return () => observer.disconnect();
  }, [nodes]);

  if (nodes.length === 0 && !isRunning) return null;

  const activateNode = (nodeId: string, source: AnchorSource) => {
    setSelectedNodeId(nodeId);
    setActiveMentionKey(null);
    const target =
      source === "console"
        ? readerRefs.current.get(nodeId)
        : consoleRefs.current.get(nodeId);
    if (typeof target?.scrollIntoView === "function") {
      target.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  };

  const renderEntityText = (text: string, nodeId: string): ReactNode => {
    if (!characterPattern) return text;

    return text.split(characterPattern).map((part, index) => {
      const character = characters.find((candidate) => candidate.name === part);
      if (!character) return part;
      const mentionKey = `${nodeId}:${character.id}:${index}`;
      return (
        <EntityMention
          key={mentionKey}
          active={activeMentionKey === mentionKey}
          character={character}
          disabled={isRunning || !simId}
          mentionKey={mentionKey}
          onOpen={setActiveMentionKey}
          onWorldUpdated={onWorldUpdated}
          simId={simId}
        />
      );
    });
  };

  return (
    <section className="story-workspace">
      <div className="story-workspace-header">
        <div>
          <div className="label">双循环工作台</div>
          <div className="story-workspace-title">内循环控制台 / 外循环小说阅读</div>
        </div>
        <div className="story-workspace-hint">
          点击任一侧节点可跳转并高亮另一侧锚点
        </div>
      </div>

      <div className="story-split">
        <aside className="story-console" ref={consolePaneRef}>
          <div className="story-pane-label">跑团控制台</div>

          {nodes.map((node) => {
            const isActive = activeNodeId === node.id;
            return (
              <div
                key={node.id}
                ref={(element) => {
                  if (element) consoleRefs.current.set(node.id, element);
                  else consoleRefs.current.delete(node.id);
                }}
                className={`console-node ${isActive ? "console-node-active" : ""}`}
                onClick={() => activateNode(node.id, "console")}
              >
                <div className="console-node-header">
                  <span>T{node.tick}</span>
                  <span>{nodeTypeLabel[node.node_type] || node.node_type}</span>
                  <span>{node.branch_id}</span>
                  {node.requires_intervention && (
                    <span className="console-node-warning">
                      {node.intervention_instruction ? "已干预" : "关键节点"}
                    </span>
                  )}
                </div>
                {buildConsoleLines(node).map((line, index) => (
                  <div key={`${node.id}-${line.role}-${index}`} className="console-line">
                    <span className={`console-avatar console-avatar-${line.tone}`}>
                      {line.role}
                    </span>
                    <span className="console-message">
                      {renderEntityText(line.body, `${node.id}:console:${index}`)}
                    </span>
                  </div>
                ))}
              </div>
            );
          })}

          <div className="harness-chips">
            <div className="story-pane-label">工程呼吸灯</div>
            {latestStatusChips.length > 0 ? (
              latestStatusChips.map((event) => (
                <span
                  key={event.event_id}
                  className="harness-chip"
                  style={{
                    borderColor: statusColor[event.level],
                    color: statusColor[event.level],
                  }}
                >
                  {buildStatusLabel(event)}
                </span>
              ))
            ) : (
              <span className="harness-chip harness-chip-muted">
                {isRunning ? "等待第一条遥测事件..." : "暂无实时遥测"}
              </span>
            )}
          </div>
        </aside>

        <main className="novel-reader" ref={readerPaneRef}>
          <div className="story-pane-label">小说阅读区</div>
          {nodes.map((node) => {
            const narrativeText = node.rendered_text || node.streaming_text || "";
            const isActive = activeNodeId === node.id;

            return (
              <article
                key={node.id}
                data-node-id={node.id}
                ref={(element) => {
                  if (element) readerRefs.current.set(node.id, element);
                  else readerRefs.current.delete(node.id);
                }}
                className={`reader-node ${isActive ? "reader-node-active" : ""}`}
                onClick={() => activateNode(node.id, "reader")}
              >
                <div className="reader-node-meta">
                  <span>T{node.tick}</span>
                  <span>{nodeTypeLabel[node.node_type] || node.node_type}</span>
                  <span>{node.branch_id === activeBranchId ? "当前世界线" : node.branch_id}</span>
                </div>
                <h2>{node.title}</h2>
                {narrativeText ? (
                  <p>
                    {renderEntityText(narrativeText, `${node.id}:reader`)}
                    {!node.rendered_text && node.streaming_text && (
                      <span className="typing-cursor">|</span>
                    )}
                  </p>
                ) : (
                  <p className="reader-placeholder">等待 Narrator 渲染正文...</p>
                )}

                {branchingEnabled && !isRunning && (
                  <button
                    className="btn"
                    style={{ fontSize: 11, padding: "6px 10px", marginTop: 12 }}
                    onClick={(event) => {
                      event.stopPropagation();
                      onForkNode(node.id);
                    }}
                  >
                    从此分叉
                  </button>
                )}
              </article>
            );
          })}

          {isRunning && (
            <div className="reader-node reader-node-active">
              <div className="reader-placeholder">
                Agent 集群正在推演下一个故事节点...
              </div>
            </div>
          )}
        </main>
      </div>
    </section>
  );
}
