// WorldBox Writer — useSimulation Hook

import { useState, useEffect, useRef, useCallback } from "react";
import type { SimulationState } from "../types";
import {
  startSimulation,
  getSimulation,
  intervene,
  exportSimulation,
} from "../utils/api";

export function useSimulation() {
  const [simId, setSimId] = useState<string | null>(null);
  const [state, setState] = useState<SimulationState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (id: string) => {
      stopPolling();
      // Poll every 1.5s for state updates
      pollRef.current = setInterval(async () => {
        try {
          const s = await getSimulation(id);
          setState(s);
          if (s.status === "complete" || s.status === "error") {
            stopPolling();
          }
        } catch (e) {
          console.error("Poll error:", e);
        }
      }, 1500);
    },
    [stopPolling]
  );

  const start = useCallback(
    async (premise: string, maxTicks = 8) => {
      setLoading(true);
      setError(null);
      setState(null);
      setSimId(null);
      try {
        const res = await startSimulation(premise, maxTicks);
        setSimId(res.sim_id);
        startPolling(res.sim_id);
        // Initial fetch
        const s = await getSimulation(res.sim_id);
        setState(s);
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    },
    [startPolling]
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
    stopPolling();
    setSimId(null);
    setState(null);
    setError(null);
    setLoading(false);
  }, [stopPolling]);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

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
