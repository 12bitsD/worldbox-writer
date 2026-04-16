// WorldBox Writer — useSimulation Hook

import { useState, useEffect, useRef, useCallback } from "react";
import type { SimulationState } from "../types";
import {
  startSimulation,
  getSimulation,
  intervene,
  exportSimulation,
  createEventStream,
} from "../utils/api";

export function useSimulation() {
  const [simId, setSimId] = useState<string | null>(null);
  const [state, setState] = useState<SimulationState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
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

  /** Fallback polling when SSE fails */
  const startFallbackPolling = useCallback(
    (id: string) => {
      if (pollRef.current) return; // already polling
      pollRef.current = setInterval(async () => {
        try {
          const s = await getSimulation(id);
          setState(s);
          if (s.status === "complete" || s.status === "error") {
            stopAll();
          }
        } catch (e) {
          console.error("Poll error:", e);
        }
      }, 1500);
    },
    [stopAll]
  );

  /** Primary: SSE real-time stream */
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
            setState((prev) => {
              if (!prev) return prev;
              // Avoid duplicate nodes
              const exists = prev.nodes.some((n) => n.id === node.id);
              if (exists) return prev;
              return {
                ...prev,
                nodes: [...prev.nodes, node as unknown as SimulationState["nodes"][0]],
              };
            });
          } else if (type === "narrator_start") {
            const node = event.node as Record<string, unknown>;
            if (!node) return;
            setState((prev) => {
              if (!prev) return prev;
              const exists = prev.nodes.some((n) => n.id === node.id);
              if (exists) return prev;
              return {
                ...prev,
                nodes: [
                  ...prev.nodes,
                  node as unknown as SimulationState["nodes"][0],
                ],
              };
            });
          } else if (type === "token") {
            const content = event.content as string;
            setState((prev) => {
              if (!prev || prev.nodes.length === 0) return prev;
              const nodes = [...prev.nodes];
              const lastIdx = nodes.length - 1;
              const lastNode = { ...nodes[lastIdx] };
              lastNode.streaming_text =
                (lastNode.streaming_text || "") + content;
              nodes[lastIdx] = lastNode;
              return { ...prev, nodes };
            });
          } else if (type === "narrator_end") {
            // Streaming done; the next "node" event will carry final rendered_text
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
        (_err) => {
          // SSE error — fallback to polling
          console.warn("SSE connection lost, falling back to polling");
          esRef.current?.close();
          esRef.current = null;
          startFallbackPolling(id);
        }
      );
    },
    [stopAll, startFallbackPolling]
  );

  const start = useCallback(
    async (premise: string, maxTicks = 8) => {
      setLoading(true);
      setError(null);
      setState(null);
      setSimId(null);
      stopAll();
      try {
        const res = await startSimulation(premise, maxTicks);
        setSimId(res.sim_id);
        // Initial fetch for immediate state
        const s = await getSimulation(res.sim_id);
        setState(s);
        // Start SSE for real-time updates
        startSSE(res.sim_id);
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    },
    [stopAll, startSSE]
  );

  const sendIntervention = useCallback(
    async (instruction: string) => {
      if (!simId) return;
      try {
        await intervene(simId, instruction);
      } catch (e) {
        setError(String(e));
      }
    },
    [simId]
  );

  const doExport = useCallback(async () => {
    if (!simId) return null;
    try {
      return await exportSimulation(simId);
    } catch (e) {
      setError(String(e));
      return null;
    }
  }, [simId]);

  const reset = useCallback(() => {
    stopAll();
    setSimId(null);
    setState(null);
    setError(null);
    setLoading(false);
  }, [stopAll]);

  useEffect(() => {
    return () => stopAll();
  }, [stopAll]);

  return {
    simId,
    state,
    loading,
    error,
    start,
    sendIntervention,
    doExport,
    reset,
  };
}
