// WorldBox Writer — TypeScript Types

export type SimStatus = "initializing" | "running" | "waiting" | "complete" | "error";

export type NodeType = "setup" | "development" | "branch" | "climax" | "resolution";

export interface Character {
  id: string;
  name: string;
  personality: string;
  goals: string[];
  status: string;
  memory: string[];
  relationships: Record<string, number>;
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
  factions: Record<string, string[]>;
  locations: Record<string, string>;
  world_rules: string[];
  constraints: Constraint[];
}

export interface StoryNode {
  id: string;
  title: string;
  description: string;
  node_type: NodeType;
  rendered_text: string;
  tick: number;
  requires_intervention: boolean;
  intervention_instruction?: string;
}

export interface SimulationState {
  sim_id: string;
  status: SimStatus;
  premise: string;
  world: WorldData | null;
  nodes: StoryNode[];
  intervention_context: string | null;
  error: string | null;
}

export interface ExportData {
  novel: string;
  world_settings: {
    title: string;
    premise: string;
    world_rules: string[];
    factions: Record<string, string[]>;
    locations: Record<string, string>;
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
