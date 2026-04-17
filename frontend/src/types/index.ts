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

export interface TelemetryEvent {
  event_id: string;
  sim_id: string;
  tick: number;
  agent: string;
  stage: string;
  level: TelemetryLevel;
  message: string;
  payload: Record<string, unknown>;
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
