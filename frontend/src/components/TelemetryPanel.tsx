import { useDeferredValue, useMemo, useState } from "react";

import type { TelemetryEvent } from "../types";

interface TelemetryPanelProps {
  events: TelemetryEvent[];
  isRunning: boolean;
}

const LEVEL_COLOR: Record<TelemetryEvent["level"], string> = {
  info: "var(--color-text-muted)",
  warning: "var(--color-warning)",
  error: "var(--color-danger)",
};

type GroupMode = "none" | "tick" | "agent";
const MAX_VISIBLE_EVENTS = 120;

function summarizePayload(payload: Record<string, unknown>): string | null {
  const previewKeys = [
    "reason",
    "hint",
    "preview",
    "node_id",
    "title",
    "context",
    "branch_id",
    "pacing",
  ];
  const parts = previewKeys
    .filter((key) => payload[key] != null)
    .map((key) => `${key}: ${String(payload[key])}`);
  return parts.length > 0 ? parts.join(" · ") : null;
}

export function TelemetryPanel({ events, isRunning }: TelemetryPanelProps) {
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [groupMode, setGroupMode] = useState<GroupMode>("tick");

  const deferredEvents = useDeferredValue(events);
  const agentOptions = useMemo(
    () => [...new Set(deferredEvents.map((event) => event.agent))].sort(),
    [deferredEvents]
  );
  const stageOptions = useMemo(
    () => [...new Set(deferredEvents.map((event) => event.stage))].sort(),
    [deferredEvents]
  );

  const filteredEvents = useMemo(() => {
    return [...deferredEvents]
      .sort((left, right) => {
        if (left.tick !== right.tick) return right.tick - left.tick;
        return right.ts.localeCompare(left.ts);
      })
      .filter((event) => agentFilter === "all" || event.agent === agentFilter)
      .filter((event) => stageFilter === "all" || event.stage === stageFilter);
  }, [agentFilter, deferredEvents, stageFilter]);
  const visibleEvents = filteredEvents.slice(0, MAX_VISIBLE_EVENTS);

  const groupedEvents = useMemo(() => {
    if (groupMode === "none") {
      return [{ label: "全部事件", events: visibleEvents }];
    }

    const groups = new Map<string, TelemetryEvent[]>();
    for (const event of visibleEvents) {
      const label = groupMode === "tick" ? `T${event.tick}` : event.agent;
      groups.set(label, [...(groups.get(label) ?? []), event]);
    }
    return [...groups.entries()].map(([label, grouped]) => ({
      label,
      events: grouped,
    }));
  }, [groupMode, visibleEvents]);

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
        <div className="label">Telemetry</div>
        <span style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
          {visibleEvents.length} / {filteredEvents.length} / {events.length} 条事件
        </span>
      </div>

      <div style={{ display: "grid", gap: 8, marginBottom: 12 }}>
        <label style={{ display: "grid", gap: 4, fontSize: 11, color: "var(--color-text-muted)" }}>
          Agent 过滤
          <select value={agentFilter} onChange={(event) => setAgentFilter(event.target.value)}>
            <option value="all">全部 Agent</option>
            {agentOptions.map((agent) => (
              <option key={agent} value={agent}>
                {agent}
              </option>
            ))}
          </select>
        </label>

        <label style={{ display: "grid", gap: 4, fontSize: 11, color: "var(--color-text-muted)" }}>
          Stage 过滤
          <select value={stageFilter} onChange={(event) => setStageFilter(event.target.value)}>
            <option value="all">全部 Stage</option>
            {stageOptions.map((stage) => (
              <option key={stage} value={stage}>
                {stage}
              </option>
            ))}
          </select>
        </label>

        <div style={{ display: "flex", gap: 6 }}>
          {(["tick", "agent", "none"] as const).map((mode) => (
            <button
              key={mode}
              className={`btn ${groupMode === mode ? "btn-primary" : ""}`}
              style={{ flex: 1, justifyContent: "center", fontSize: 11, padding: "6px 10px" }}
              onClick={() => setGroupMode(mode)}
            >
              {mode === "tick" ? "按 Tick" : mode === "agent" ? "按 Agent" : "不分组"}
            </button>
          ))}
        </div>
      </div>

      {filteredEvents.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          {events.length === 0
            ? isRunning
              ? "等待第一条关键事件..."
              : "当前会话还没有遥测事件。"
            : "当前筛选条件下没有匹配事件。"}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {visibleEvents.length < filteredEvents.length && (
            <div style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
              当前仅渲染最近 {MAX_VISIBLE_EVENTS} 条匹配事件，以保证长会话可读性。
            </div>
          )}
          {groupedEvents.map((group) => (
            <div key={group.label}>
              {groupMode !== "none" && (
                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: "var(--color-text-muted)",
                    marginBottom: 6,
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                  }}
                >
                  {group.label}
                </div>
              )}

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {group.events.map((event) => {
                  const payloadSummary = summarizePayload(event.payload);
                  return (
                    <div
                      key={event.event_id}
                      className="card card-sm"
                      style={{
                        borderLeft: `3px solid ${LEVEL_COLOR[event.level]}`,
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: 8,
                          marginBottom: 4,
                        }}
                      >
                        <span style={{ fontWeight: 700, fontSize: 12 }}>
                          {event.agent}
                        </span>
                        <span style={{ fontSize: 10, color: "var(--color-text-muted)" }}>
                          T{event.tick}
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>
                        {event.message}
                      </div>

                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          marginTop: 6,
                          flexWrap: "wrap",
                        }}
                      >
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
                          {event.stage}
                        </span>
                        <span
                          style={{
                            fontSize: 10,
                            padding: "1px 6px",
                            border: "1px solid var(--color-border)",
                            color: "var(--color-text-muted)",
                            textTransform: "uppercase",
                          }}
                        >
                          {event.span_kind}
                        </span>
                        <span
                          style={{
                            fontSize: 10,
                            padding: "1px 6px",
                            border: "1px solid var(--color-border)",
                            color:
                              event.branch_id === "main"
                                ? "var(--color-text-muted)"
                                : "var(--color-warning)",
                          }}
                        >
                          {event.branch_id}
                        </span>
                        {event.request_id && (
                          <span style={{ fontSize: 10, color: "var(--color-text-muted)", fontFamily: "monospace" }}>
                            req: {event.request_id}
                          </span>
                        )}
                        <span style={{ fontSize: 10, color: "var(--color-text-muted)", fontFamily: "monospace" }}>
                          trace: {event.trace_id}
                        </span>
                        {event.parent_event_id && (
                          <span style={{ fontSize: 10, color: "var(--color-text-muted)", fontFamily: "monospace" }}>
                            parent: {event.parent_event_id}
                          </span>
                        )}
                        {event.forked_from_node_id && (
                          <span style={{ fontSize: 10, color: "var(--color-text-muted)", fontFamily: "monospace" }}>
                            fork: {event.forked_from_node_id}
                          </span>
                        )}
                        {event.provider && (
                          <span style={{ fontSize: 10, color: "var(--color-text-muted)" }}>
                            {event.provider}/{event.model}
                          </span>
                        )}
                        {event.duration_ms != null && (
                          <span style={{ fontSize: 10, color: "var(--color-text-muted)" }}>
                            {event.duration_ms}ms
                          </span>
                        )}
                      </div>

                      {payloadSummary && (
                        <div
                          style={{
                            fontSize: 10,
                            color: "var(--color-text-muted)",
                            marginTop: 6,
                            lineHeight: 1.5,
                          }}
                        >
                          {payloadSummary}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
