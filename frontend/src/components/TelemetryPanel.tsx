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

export function TelemetryPanel({ events, isRunning }: TelemetryPanelProps) {
  const visibleEvents = [...events].slice(-16).reverse();

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
          {events.length} 条事件
        </span>
      </div>

      {visibleEvents.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          {isRunning ? "等待第一条关键事件..." : "当前会话还没有遥测事件。"}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {visibleEvents.map((event) => (
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
                {Object.keys(event.payload).length > 0 && (
                  <span
                    style={{
                      fontSize: 10,
                      color: "var(--color-text-muted)",
                      fontFamily: "monospace",
                    }}
                  >
                    {JSON.stringify(event.payload)}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
