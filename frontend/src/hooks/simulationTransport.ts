import { useCallback, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { SimulationState } from "../types";
import { createEventStream, getSimulation } from "../utils/api";
import {
  appendStreamingToken,
  mergeSimulationSnapshot,
  mergeTelemetryEvents,
  upsertNode,
} from "./simulationState";

interface SimulationTransportOptions {
  setState: Dispatch<SetStateAction<SimulationState | null>>;
  refreshBranchCompare: (simId: string) => Promise<void>;
}

export function isStreamingStatus(status: SimulationState["status"]): boolean {
  return status === "running" || status === "waiting" || status === "initializing";
}

export function useSimulationTransport({
  setState,
  refreshBranchCompare,
}: SimulationTransportOptions) {
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopAll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  const startFallbackPolling = useCallback(
    (id: string) => {
      if (pollRef.current) return;
      pollRef.current = setInterval(async () => {
        try {
          const snapshot = await getSimulation(id);
          setState((prev) => mergeSimulationSnapshot(prev, snapshot));
          if (snapshot.features.branching_enabled) {
            void refreshBranchCompare(id);
          }
          if (snapshot.status === "complete" || snapshot.status === "error") {
            stopAll();
          }
        } catch (error) {
          console.error("Poll error:", error);
        }
      }, 1500);
    },
    [refreshBranchCompare, setState, stopAll]
  );

  const startSSE = useCallback(
    (id: string) => {
      if (esRef.current) {
        esRef.current.close();
      }

      esRef.current = createEventStream(
        id,
        (event) => {
          const type = event.type as string;

          if (type === "node") {
            const node = event.data as Record<string, unknown>;
            const nextWorld = (event.world as SimulationState["world"]) ?? null;
            setState((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                world: nextWorld ?? prev.world,
                nodes: upsertNode(
                  prev.nodes,
                  node as unknown as SimulationState["nodes"][0]
                ),
              };
            });
          } else if (type === "narrator_start") {
            const node = event.node as Record<string, unknown>;
            if (!node) return;
            setState((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                nodes: upsertNode(
                  prev.nodes,
                  node as unknown as SimulationState["nodes"][0]
                ),
              };
            });
          } else if (type === "narrator_end") {
            // Streaming finished for the active narrator node. Future
            // sprints can mark a node as "complete" or surface render
            // progress here; for now we no-op so the contract test
            // doesn't fail when the backend emits this event.
          } else if (type === "token") {
            const content = event.content as string;
            const nodeId = event.node_id as string | undefined;
            setState((prev) => {
              if (!prev || prev.nodes.length === 0) return prev;
              return {
                ...prev,
                nodes: appendStreamingToken(prev.nodes, content, nodeId),
              };
            });
          } else if (type === "telemetry") {
            const telemetry = event.data as SimulationState["telemetry"][0];
            setState((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                telemetry: mergeTelemetryEvents(prev.telemetry, [telemetry]),
              };
            });
          } else if (type === "intervention") {
            setState((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                status: "waiting",
                intervention_context: event.context as string,
              };
            });
          } else if (type === "status") {
            const status = event.status as string;
            setState((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                status: status as SimulationState["status"],
                error: (event.error as string) ?? prev.error,
              };
            });
            if (status === "complete" || status === "error") {
              stopAll();
            }
          }
        },
        () => {
          console.warn("SSE connection lost, falling back to polling");
          esRef.current?.close();
          esRef.current = null;
          startFallbackPolling(id);
        }
      );
    },
    [setState, startFallbackPolling, stopAll]
  );

  return { startSSE, stopAll };
}
