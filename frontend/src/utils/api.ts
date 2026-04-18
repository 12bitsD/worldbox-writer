// WorldBox Writer — API Client

import type {
  BranchCompareResponse,
  ExportData,
  SimulationState,
} from "../types";

const BASE = "/api";

export async function startSimulation(
  premise: string,
  maxTicks = 8
): Promise<{ sim_id: string; status: string; message: string }> {
  const res = await fetch(`${BASE}/simulate/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ premise, max_ticks: maxTicks }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSimulation(
  simId: string,
  branchId?: string
): Promise<SimulationState> {
  const query = branchId ? `?branch=${encodeURIComponent(branchId)}` : "";
  const res = await fetch(`${BASE}/simulate/${simId}${query}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function intervene(
  simId: string,
  instruction: string
): Promise<void> {
  const res = await fetch(`${BASE}/simulate/${simId}/intervene`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function exportSimulation(
  simId: string,
  branchId?: string
): Promise<ExportData> {
  const query = branchId ? `?branch=${encodeURIComponent(branchId)}` : "";
  const res = await fetch(`${BASE}/simulate/${simId}/export${query}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createBranch(
  simId: string,
  input: {
    source_node_id: string;
    label?: string;
    switch_immediately?: boolean;
    continue_simulation?: boolean;
    pacing?: "calm" | "balanced" | "intense";
  }
): Promise<SimulationState> {
  const res = await fetch(`${BASE}/simulate/${simId}/branch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function switchBranch(
  simId: string,
  branchId: string
): Promise<SimulationState> {
  const res = await fetch(`${BASE}/simulate/${simId}/branch/switch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ branch_id: branchId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function compareBranches(
  simId: string
): Promise<BranchCompareResponse> {
  const res = await fetch(`${BASE}/simulate/${simId}/branch/compare`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateBranchPacing(
  simId: string,
  branchId: string,
  pacing: "calm" | "balanced" | "intense"
): Promise<void> {
  const res = await fetch(`${BASE}/simulate/${simId}/branch/pacing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ branch_id: branchId, pacing }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function listSessions(): Promise<
  Array<{
    sim_id: string;
    status: string;
    premise: string;
    nodes_count: number;
  }>
> {
  const res = await fetch(`${BASE}/sessions`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateCharacter(
  simId: string,
  characterId: string,
  updates: {
    name?: string;
    description?: string;
    personality?: string;
    goals?: string[];
    status?: string;
  }
): Promise<void> {
  const res = await fetch(`${BASE}/simulate/${simId}/characters/${characterId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function updateWorld(
  simId: string,
  updates: {
    title?: string;
    premise?: string;
    world_rules?: string[];
  }
): Promise<void> {
  const res = await fetch(`${BASE}/simulate/${simId}/world`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function addConstraint(
  simId: string,
  constraint: {
    name: string;
    description: string;
    constraint_type: string;
    severity: string;
    rule: string;
  }
): Promise<void> {
  const res = await fetch(`${BASE}/simulate/${simId}/constraints`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(constraint),
  });
  if (!res.ok) throw new Error(await res.text());
}

export function createEventStream(
  simId: string,
  onEvent: (event: { type: string; [key: string]: unknown }) => void,
  onError?: (err: Event) => void
): EventSource {
  const es = new EventSource(`${BASE}/simulate/${simId}/stream`);
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
    } catch {
      // ignore parse errors
    }
  };
  if (onError) es.onerror = onError;
  return es;
}
