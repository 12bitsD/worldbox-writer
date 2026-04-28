// WorldBox Writer — useSimulation Hook

import { useState, useEffect, useRef, useCallback } from "react";
import type {
  BranchCompareResponse,
  SessionSummary,
  SimulationState,
} from "../types";
import {
  compareBranches,
  createBranch,
  switchBranch,
  startSimulation,
  getSimulation,
  intervene,
  exportSimulation,
  createEventStream,
  listSessions,
  updateBranchPacing,
} from "../utils/api";
import {
  appendStreamingToken,
  mergeSimulationSnapshot,
  mergeTelemetryEvents,
  upsertNode,
} from "./simulationState";

const LAST_SIM_ID_KEY = "worldbox:last-sim-id";

export function shouldAutoRestoreSession(status: SimulationState["status"]): boolean {
  return status !== "error" && status !== "initializing";
}

export function useSimulation() {
  const [simId, setSimId] = useState<string | null>(null);
  const [state, setState] = useState<SimulationState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [branchCompare, setBranchCompare] =
    useState<BranchCompareResponse["branches"] | null>(null);
  const [recentSessions, setRecentSessions] = useState<SessionSummary[]>([]);
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

  const refreshBranchCompare = useCallback(async (id: string) => {
    try {
      const compare = await compareBranches(id);
      setBranchCompare(compare.branches);
    } catch {
      setBranchCompare(null);
    }
  }, []);

  /** Fallback polling when SSE fails */
  const startFallbackPolling = useCallback(
    (id: string) => {
      if (pollRef.current) return; // already polling
      pollRef.current = setInterval(async () => {
        try {
          const s = await getSimulation(id);
          setState((prev) => mergeSimulationSnapshot(prev, s));
          if (s.features.branching_enabled) {
            void refreshBranchCompare(id);
          }
          if (s.status === "complete" || s.status === "error") {
            stopAll();
          }
        } catch (e) {
          console.error("Poll error:", e);
        }
      }, 1500);
    },
    [refreshBranchCompare, stopAll]
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
          } else if (type === "narrator_end") {
            // Streaming done; the next "node" event will carry final rendered_text
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
    async (id: string, options?: { autoRestore?: boolean }) => {
      setLoading(true);
      setError(null);
      stopAll();
      try {
        const nextState = await getSimulation(id);
        if (
          options?.autoRestore &&
          !shouldAutoRestoreSession(nextState.status)
        ) {
          window.sessionStorage.removeItem(LAST_SIM_ID_KEY);
          return;
        }
        setSimId(id);
        setState((prev) => mergeSimulationSnapshot(prev, nextState));
        if (nextState.features.branching_enabled) {
          void refreshBranchCompare(id);
        } else {
          setBranchCompare(null);
        }
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
    [refreshBranchCompare, refreshRecentSessions, startSSE, stopAll]
  );

  const refresh = useCallback(async () => {
    if (!simId) return;
    try {
      const nextState = await getSimulation(simId);
      setState((prev) => mergeSimulationSnapshot(prev, nextState));
      if (nextState.features.branching_enabled) {
        void refreshBranchCompare(simId);
      }
    } catch (e) {
      setError(String(e));
    }
  }, [refreshBranchCompare, simId]);

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

        // Publish an immediate placeholder state so the UI can attach SSE
        // and render telemetry/progress before the first snapshot completes.
        setState({
          sim_id: res.sim_id,
          status: res.status as SimulationState["status"],
          premise,
          world: null,
          nodes: [],
          telemetry: [],
          intervention_context: null,
          error: null,
          features: { branching_enabled: false, dual_loop_enabled: false },
        });

        // Start SSE first so early telemetry and narrator tokens are not gated
        // behind an extra round-trip for the initial GET snapshot.
        startSSE(res.sim_id);

        // Initial fetch for structured state reconciliation.
        const s = await getSimulation(res.sim_id);
        setState((prev) => mergeSimulationSnapshot(prev, s));
        if (s.features.branching_enabled) {
          void refreshBranchCompare(res.sim_id);
        } else {
          setBranchCompare(null);
        }
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    },
    [refreshBranchCompare, refreshRecentSessions, startSSE, stopAll]
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
      return await exportSimulation(simId, state?.world?.active_branch_id);
    } catch (e) {
      setError(String(e));
      return null;
    }
  }, [simId, state?.world?.active_branch_id]);

  const forkAtNode = useCallback(
    async (
      sourceNodeId: string,
      options?: {
        label?: string;
        pacing?: "calm" | "balanced" | "intense";
        continueSimulation?: boolean;
      }
    ) => {
      if (!simId) return;
      try {
        const nextState = await createBranch(simId, {
          source_node_id: sourceNodeId,
          label: options?.label,
          pacing: options?.pacing,
          continue_simulation: options?.continueSimulation ?? true,
          switch_immediately: true,
        });
        setState(nextState);
        void refreshBranchCompare(simId);
        if (
          nextState.status === "running" ||
          nextState.status === "waiting" ||
          nextState.status === "initializing"
        ) {
          startSSE(simId);
        }
      } catch (e) {
        setError(String(e));
      }
    },
    [refreshBranchCompare, simId, startSSE]
  );

  const activateBranch = useCallback(
    async (branchId: string) => {
      if (!simId) return;
      try {
        const nextState = await switchBranch(simId, branchId);
        setState(nextState);
        void refreshBranchCompare(simId);
      } catch (e) {
        setError(String(e));
      }
    },
    [refreshBranchCompare, simId]
  );

  const setBranchPacing = useCallback(
    async (
      branchId: string,
      pacing: "calm" | "balanced" | "intense"
    ) => {
      if (!simId) return;
      try {
        await updateBranchPacing(simId, branchId, pacing);
        await refresh();
      } catch (e) {
        setError(String(e));
      }
    },
    [refresh, simId]
  );

  const reset = useCallback(() => {
    stopAll();
    setSimId(null);
    setState(null);
    setError(null);
    setLoading(false);
    setBranchCompare(null);
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
    void openSession(storedId, { autoRestore: true });
  }, [openSession]);

  return {
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
    refreshRecentSessions,
    reset,
  };
}
