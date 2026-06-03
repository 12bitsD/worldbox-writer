import { useCallback } from "react";
import type { Dispatch, SetStateAction } from "react";
import type {
  BranchCompareResponse,
  ExportData,
  SessionSummary,
  SimulationState,
} from "../types";
import {
  createBranch,
  exportSimulation,
  getSimulation,
  intervene,
  listSessions,
  startSimulation,
  switchBranch,
  updateBranchPacing,
} from "../utils/api";
import { mergeSimulationSnapshot } from "./simulationState";
import { isStreamingStatus } from "./simulationTransport";

export const LAST_SIM_ID_KEY = "worldbox:last-sim-id";

export function shouldAutoRestoreSession(status: SimulationState["status"]): boolean {
  return status !== "error" && status !== "initializing";
}

interface SimulationActionsOptions {
  simId: string | null;
  state: SimulationState | null;
  setSimId: Dispatch<SetStateAction<string | null>>;
  setState: Dispatch<SetStateAction<SimulationState | null>>;
  setLoading: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  setBranchCompare: Dispatch<
    SetStateAction<BranchCompareResponse["branches"] | null>
  >;
  setRecentSessions: Dispatch<SetStateAction<SessionSummary[]>>;
  refreshBranchCompare: (simId: string) => Promise<void>;
  startSSE: (simId: string) => void;
  stopAll: () => void;
}

export function useSimulationActions({
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
}: SimulationActionsOptions) {
  const refreshRecentSessions = useCallback(() => {
    return listSessions()
      .then((sessions) => {
        setRecentSessions(sessions);
      })
      .catch(() => {
        // ignore recent session load errors
      });
  }, [setRecentSessions]);

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

        if (isStreamingStatus(nextState.status)) {
          startSSE(id);
        }
      } catch (error) {
        setError(String(error));
        window.sessionStorage.removeItem(LAST_SIM_ID_KEY);
      } finally {
        setLoading(false);
      }
    },
    [
      refreshBranchCompare,
      refreshRecentSessions,
      setBranchCompare,
      setError,
      setLoading,
      setSimId,
      setState,
      startSSE,
      stopAll,
    ]
  );

  const refresh = useCallback(async () => {
    if (!simId) return;
    try {
      const nextState = await getSimulation(simId);
      setState((prev) => mergeSimulationSnapshot(prev, nextState));
      if (nextState.features.branching_enabled) {
        void refreshBranchCompare(simId);
      }
    } catch (error) {
      setError(String(error));
    }
  }, [refreshBranchCompare, setError, setState, simId]);

  const start = useCallback(
    async (premise: string, maxTicks = 8) => {
      setLoading(true);
      setError(null);
      setState(null);
      setSimId(null);
      stopAll();
      try {
        const response = await startSimulation(premise, maxTicks);
        setSimId(response.sim_id);
        window.sessionStorage.setItem(LAST_SIM_ID_KEY, response.sim_id);
        void refreshRecentSessions();

        setState({
          sim_id: response.sim_id,
          status: response.status as SimulationState["status"],
          premise,
          world: null,
          nodes: [],
          telemetry: [],
          intervention_context: null,
          error: null,
          features: { branching_enabled: false, dual_loop_enabled: false },
        });

        startSSE(response.sim_id);

        const nextState = await getSimulation(response.sim_id);
        setState((prev) => mergeSimulationSnapshot(prev, nextState));
        if (nextState.features.branching_enabled) {
          void refreshBranchCompare(response.sim_id);
        } else {
          setBranchCompare(null);
        }
      } catch (error) {
        setError(String(error));
      } finally {
        setLoading(false);
      }
    },
    [
      refreshBranchCompare,
      refreshRecentSessions,
      setBranchCompare,
      setError,
      setLoading,
      setSimId,
      setState,
      startSSE,
      stopAll,
    ]
  );

  const sendIntervention = useCallback(
    async (instruction: string) => {
      if (!simId) return;
      try {
        await intervene(simId, instruction);
      } catch (error) {
        setError(String(error));
      }
    },
    [setError, simId]
  );

  const doExport = useCallback(async (): Promise<ExportData | null> => {
    if (!simId) return null;
    try {
      return await exportSimulation(simId, state?.world?.active_branch_id);
    } catch (error) {
      setError(String(error));
      return null;
    }
  }, [setError, simId, state?.world?.active_branch_id]);

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
        if (isStreamingStatus(nextState.status)) {
          startSSE(simId);
        }
      } catch (error) {
        setError(String(error));
      }
    },
    [refreshBranchCompare, setError, setState, simId, startSSE]
  );

  const activateBranch = useCallback(
    async (branchId: string) => {
      if (!simId) return;
      try {
        const nextState = await switchBranch(simId, branchId);
        setState(nextState);
        void refreshBranchCompare(simId);
      } catch (error) {
        setError(String(error));
      }
    },
    [refreshBranchCompare, setError, setState, simId]
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
      } catch (error) {
        setError(String(error));
      }
    },
    [refresh, setError, simId]
  );

  return {
    refreshRecentSessions,
    openSession,
    refresh,
    start,
    sendIntervention,
    doExport,
    forkAtNode,
    activateBranch,
    setBranchPacing,
  };
}
