import { useMemo } from "react";

import type { TelemetryEvent } from "../types";

interface ProgressPanelProps {
  events: TelemetryEvent[];
  isRunning: boolean;
}

type StepStatus = "done" | "current" | "pending";

interface ProgressStep {
  key: string;
  label: string;
  description: string;
  status: StepStatus;
}

function buildSteps(events: TelemetryEvent[], isRunning: boolean): ProgressStep[] {
  const hasWorldInit = events.some(
    (event) => event.agent === "director" && event.stage === "world_initialized"
  );
  const hasNodeCommitted = events.some(
    (event) => event.agent === "node_detector" && event.stage === "node_committed"
  );
  const hasNarratorStarted = events.some(
    (event) => event.agent === "narrator" && event.stage === "started"
  );
  const hasNarratorCompleted = events.some(
    (event) => event.agent === "narrator" && event.stage === "completed"
  );
  const hasWorldEnriched = events.some(
    (event) => event.agent === "world_builder" && event.stage === "world_enriched"
  );

  const currentStep = !hasWorldInit
    ? "world"
    : !hasNodeCommitted
      ? "scene"
      : !hasNarratorCompleted
        ? "narration"
        : isRunning && !hasWorldEnriched
          ? "enrichment"
          : null;

  const resolveStatus = (
    key: string,
    done: boolean
  ): StepStatus => {
    if (done) return "done";
    if (currentStep === key) return "current";
    return "pending";
  };

  return [
    {
      key: "world",
      label: "启动世界",
      description: "Director 正在解析前提、角色与约束",
      status: resolveStatus("world", hasWorldInit),
    },
    {
      key: "scene",
      label: "生成第一幕",
      description: "Actor / GateKeeper / NodeDetector 正在生成首个节点",
      status: resolveStatus("scene", hasNodeCommitted),
    },
    {
      key: "narration",
      label: hasNarratorStarted && !hasNarratorCompleted ? "正在出字" : "渐进出字",
      description: "Narrator 已进入正文流式输出",
      status: resolveStatus("narration", hasNarratorCompleted),
    },
    {
      key: "enrichment",
      label: "补全世界细节",
      description: "WorldBuilder 在第一幕可见后补齐设定",
      status: resolveStatus("enrichment", hasWorldEnriched),
    },
  ];
}

export function ProgressPanel({ events, isRunning }: ProgressPanelProps) {
  const steps = useMemo(() => buildSteps(events, isRunning), [events, isRunning]);
  const latestEvent = events.length > 0 ? events[events.length - 1] : null;
  const recentEvents = useMemo(
    () => [...events].slice(-3).reverse(),
    [events]
  );

  return (
    <div
      className="card"
      style={{
        padding: 16,
        marginBottom: 16,
        background: "linear-gradient(180deg, rgba(15, 23, 42, 0.02), rgba(15, 23, 42, 0.06))",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 12,
        }}
      >
        <div>
          <div className="label" style={{ marginBottom: 6 }}>
            首次推演进度
          </div>
          <div style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
            {latestEvent
              ? latestEvent.message
              : "已启动推演，等待第一条阶段进度..."}
          </div>
        </div>
        <span
          style={{
            fontSize: 11,
            color: isRunning ? "var(--color-warning)" : "var(--color-text-muted)",
            border: "1px solid var(--color-border)",
            padding: "3px 8px",
          }}
        >
          {isRunning ? "处理中" : "已停止"}
        </span>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
          gap: 10,
          marginBottom: 12,
        }}
      >
        {steps.map((step, index) => (
          <div
            key={step.key}
            style={{
              padding: 12,
              border: "1px solid var(--color-border)",
              background:
                step.status === "current"
                  ? "rgba(217, 119, 6, 0.08)"
                  : step.status === "done"
                    ? "rgba(5, 150, 105, 0.08)"
                    : "var(--color-bg-card)",
            }}
          >
            <div
              style={{
                fontSize: 10,
                color: "var(--color-text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: 6,
              }}
            >
              Step {index + 1}
            </div>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
              {step.label}
            </div>
            <div style={{ fontSize: 11, color: "var(--color-text-secondary)", lineHeight: 1.5 }}>
              {step.description}
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gap: 6 }}>
        {recentEvents.length > 0 ? (
          recentEvents.map((event) => (
            <div
              key={event.event_id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                fontSize: 11,
                color: "var(--color-text-secondary)",
                borderTop: "1px solid var(--color-border-light)",
                paddingTop: 6,
              }}
            >
              <span>
                {event.agent} / {event.stage} / {event.message}
              </span>
              <span style={{ color: "var(--color-text-muted)", fontFamily: "monospace" }}>
                {event.duration_ms != null ? `${event.duration_ms}ms` : `T${event.tick}`}
              </span>
            </div>
          ))
        ) : (
          <div style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
            当前还没有阶段事件，通常会在首个 LLM 调用返回后出现。
          </div>
        )}
      </div>
    </div>
  );
}
