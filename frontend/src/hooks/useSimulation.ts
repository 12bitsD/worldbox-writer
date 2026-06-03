// WorldBox Writer — useSimulation Hook

import { useCallback, useEffect, useState } from "react";
import type {
  BranchCompareResponse,
  SessionSummary,
  SimulationState,
} from "../types";
import { compareBranches } from "../utils/api";
import {
  LAST_SIM_ID_KEY,
  shouldAutoRestoreSession,
  useSimulationActions,
} from "./simulationActions";
import { useSimulationTransport } from "./simulationTransport";

export { shouldAutoRestoreSession };

export function useSimulation() {
  const [simId, setSimId] = useState<string | null>(null);
  const [state, setState] = useState<SimulationState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [branchCompare, setBranchCompare] =
    useState<BranchCompareResponse["branches"] | null>(null);
  const [recentSessions, setRecentSessions] = useState<SessionSummary[]>([]);

  const refreshBranchCompare = useCallback(async (id: string) => {
    try {
      const compare = await compareBranches(id);
      setBranchCompare(compare.branches);
    } catch {
      setBranchCompare(null);
    }
  }, []);

  const { startSSE, stopAll } = useSimulationTransport({
    setState,
    refreshBranchCompare,
  });

  const {
    refreshRecentSessions,
    openSession,
    refresh,
    start,
    sendIntervention,
    doExport,
    forkAtNode,
    activateBranch,
    setBranchPacing,
  } = useSimulationActions({
    simId,
    state,
    setSimId,
    setState,
    setLoading,
    setError,
    setBranchCompare,
    setRecentSessions,
    refreshBranchCompare,
    startSSE,
    stopAll,
  });

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
