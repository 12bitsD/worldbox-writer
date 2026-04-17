// WorldBox Writer — useSimulation Hook

import { useState, useEffect, useRef, useCallback } from "react";
import type { SimulationState } from "../types";
import {
  startSimulation,
  getSimulation,
  intervene,
  exportSimulation,
  createEventStream,
  listSessions,
} from "../utils/api";

const LAST_SIM_ID_KEY = "worldbox:last-sim-id";

export function useSimulation() {
  const [simId, setSimId] = useState<string | null>(null);
  const [state, setState] = useState<SimulationState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recentSessions, setRecentSessions] = useState<
    Array<{
      sim_id: string;
      status: string;
      premise: string;
      nodes_count: number;
    }>
  >([]);
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

  const refreshRecentSessions = useCallback(() => {
    return listSessions()
      .then((sessions) => {
        setRecentSessions(sessions);
      })
      .catch(() => {
        // ignore recent session load errors
      });
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
          } else if (type === "telemetry") {
            const telemetry = event.data as SimulationState["telemetry"][0];
            setState((prev) => {
              if (!prev) return prev;
              const exists = prev.telemetry.some(
                (item) => item.event_id === telemetry.event_id
              );
              if (exists) return prev;
              return {
                ...prev,
                telemetry: [...prev.telemetry, telemetry],
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

  const openSession = useCallback(
    async (id: string) => {
      setLoading(true);
      setError(null);
      stopAll();
      try {
        const nextState = await getSimulation(id);
        setSimId(id);
        setState(nextState);
        window.sessionStorage.setItem(LAST_SIM_ID_KEY, id);
        void refreshRecentSessions();

        if (
          nextState.status === "running" ||
          nextState.status === "waiting" ||
          nextState.status === "initializing"
        ) {
          startSSE(id);
        }
      } catch (e) {
        setError(String(e));
        window.sessionStorage.removeItem(LAST_SIM_ID_KEY);
      } finally {
        setLoading(false);
      }
    },
    [refreshRecentSessions, startSSE, stopAll]
  );

  const refresh = useCallback(async () => {
    if (!simId) return;
    try {
      const nextState = await getSimulation(simId);
      setState(nextState);
    } catch (e) {
      setError(String(e));
    }
  }, [simId]);

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
        window.sessionStorage.setItem(LAST_SIM_ID_KEY, res.sim_id);
        void refreshRecentSessions();
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
    [refreshRecentSessions, startSSE, stopAll]
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
    window.sessionStorage.removeItem(LAST_SIM_ID_KEY);
  }, [stopAll]);

  useEffect(() => {
    return () => stopAll();
  }, [stopAll]);

  useEffect(() => {
    void refreshRecentSessions();
  }, [refreshRecentSessions]);

  useEffect(() => {
    const storedId = window.sessionStorage.getItem(LAST_SIM_ID_KEY);
    if (!storedId) return;
    void openSession(storedId);
  }, [openSession]);

  return {
    simId,
    state,
    loading,
    error,
    recentSessions,
    start,
    openSession,
    sendIntervention,
    doExport,
    refresh,
    refreshRecentSessions,
    reset,
  };
}
