// WorldBox Writer — TypeScript Types

export type SimStatus = "initializing" | "running" | "waiting" | "complete" | "error";

export type NodeType = "setup" | "development" | "branch" | "climax" | "resolution";

export interface WorldEntity {
  name: string;
  description?: string;
  [key: string]: unknown;
}

export type RelationshipLabel =
  | "ally"
  | "neutral"
  | "rival"
  | "fear"
  | "trust"
  | "unknown";

export interface Relationship {
  target_id: string;
  affinity: number;
  label: RelationshipLabel;
  note: string;
  updated_at_tick: number | null;
}

export type TelemetryLevel = "info" | "warning" | "error";
export type TelemetrySpanKind = "event" | "llm" | "user" | "system";

export interface TelemetryEvent {
  event_id: string;
  sim_id: string;
  trace_id: string;
  request_id: string | null;
  parent_event_id: string | null;
  tick: number;
  agent: string;
  stage: string;
  level: TelemetryLevel;
  span_kind: TelemetrySpanKind;
  message: string;
  payload: Record<string, unknown>;
  provider: string | null;
  model: string | null;
  duration_ms: number | null;
  branch_id: string;
  forked_from_node_id: string | null;
  source_branch_id: string | null;
  source_sim_id: string | null;
  ts: string;
}

export interface Character {
  id: string;
  name: string;
  personality: string;
  goals: string[];
  status: string;
  memory: string[];
  relationships: Record<string, Relationship>;
}

export interface Constraint {
  name: string;
  rule: string;
  severity: string;
  type: string;
}

export interface BranchMeta {
  label: string;
  forked_from_node: string | null;
  source_branch_id?: string | null;
  source_sim_id?: string | null;
  created_at_tick?: number;
  latest_node_id?: string | null;
  latest_tick?: number;
  last_node_summary?: string | null;
  nodes_count?: number;
  status?: SimStatus;
  pacing?: "calm" | "balanced" | "intense";
}

export interface BranchCompareSummary {
  branch_id: string;
  label: string;
  forked_from_node: string | null;
  source_branch_id: string | null;
  source_sim_id: string | null;
  created_at_tick: number;
  latest_node_id: string | null;
  latest_tick: number;
  nodes_count: number;
  last_node_summary: string | null;
  status: SimStatus;
  pacing: "calm" | "balanced" | "intense";
  is_active: boolean;
}

export interface SimulationFeatures {
  branching_enabled: boolean;
}

export interface WorldData {
  title: string;
  premise: string;
  tick: number;
  is_complete: boolean;
  characters: Character[];
  factions: WorldEntity[];
  locations: WorldEntity[];
  world_rules: string[];
  constraints: Constraint[];
  // ---- Branching & Merging (reserved for Sprint 8+) ----
  branches: Record<string, BranchMeta>;
  active_branch_id: string;
}

export interface StoryNode {
  id: string;
  title: string;
  description: string;
  node_type: NodeType;
  rendered_text: string | null;
  tick: number;
  requires_intervention: boolean;
  intervention_instruction?: string;
  streaming_text?: string;
  parent_ids: string[];
  // ---- Branching & Merging (reserved for Sprint 8+) ----
  branch_id: string; // "main" by default
  merged_from_ids: string[]; // source branch node IDs on merge
}

export interface SimulationState {
  sim_id: string;
  status: SimStatus;
  premise: string;
  world: WorldData | null;
  nodes: StoryNode[];
  telemetry: TelemetryEvent[];
  intervention_context: string | null;
  error: string | null;
  features: SimulationFeatures;
}

export interface BranchCompareResponse {
  sim_id: string;
  active_branch_id: string;
  branches: Record<string, BranchCompareSummary>;
}

export interface ExportData {
  novel: string;
  world_settings: {
    title: string;
    premise: string;
    world_rules: string[];
    factions: WorldEntity[];
    locations: WorldEntity[];
    characters: Array<{
      name: string;
      personality: string;
      goals: string[];
      status: string;
    }>;
  };
  timeline: Array<{
    tick: number;
    title: string;
    type: string;
    description: string;
    intervention?: string;
  }>;
}
