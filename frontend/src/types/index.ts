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
  description?: string;
  personality: string;
  goals: string[];
  status: string;
  memory: string[];
  relationships: Record<string, Relationship>;
}

export interface Constraint {
  id?: string;
  name: string;
  description?: string;
  rule: string;
  severity: string;
  type: string;
  is_active?: boolean;
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
  dual_loop_enabled: boolean;
}

export interface MemoryRecallTrace {
  trace_id: string;
  character_id: string | null;
  query: string;
  working_memory: string[];
  episodic_memory_snippets: string[];
  reflective_memory: string[];
  metadata: Record<string, unknown>;
}

export interface PromptTrace {
  trace_id: string;
  agent: string;
  scene_id: string;
  character_id: string | null;
  system_prompt: string;
  user_prompt: string;
  assembled_prompt: string;
  narrative_pressure: string;
  visible_character_ids: string[];
  memory_trace: MemoryRecallTrace | null;
  metadata: Record<string, unknown>;
}

export interface ActionIntent {
  intent_id: string;
  scene_id: string;
  actor_id: string;
  actor_name: string;
  action_type: string;
  summary: string;
  rationale: string;
  target_ids: string[];
  confidence: number;
  prompt_trace_id: string | null;
  metadata: Record<string, unknown>;
}

export interface IntentCritique {
  critique_id: string;
  scene_id: string;
  intent_id: string;
  actor_id: string;
  actor_name: string;
  accepted: boolean;
  reason_code: string;
  severity: string;
  reason: string;
  revision_hint: string;
  metadata: Record<string, unknown>;
}

export interface SceneBeat {
  beat_id: string;
  actor_id: string | null;
  actor_name: string | null;
  summary: string;
  outcome: string;
  visibility: string;
  source_intent_id: string | null;
  metadata: Record<string, unknown>;
}

export interface ScenePlan {
  scene_id: string;
  branch_id: string;
  tick: number;
  title: string;
  objective: string;
  conflict_type: string;
  suspense_hook: string;
  setting: string;
  public_summary: string;
  spotlight_character_ids: string[];
  narrative_pressure: string;
  constraints: string[];
  source_node_id: string | null;
  metadata: Record<string, unknown>;
}

export interface SceneScript {
  script_id: string;
  scene_id: string;
  branch_id: string;
  tick: number;
  title: string;
  summary: string;
  public_facts: string[];
  participating_character_ids: string[];
  accepted_intent_ids: string[];
  rejected_intent_ids: string[];
  beats: SceneBeat[];
  source_node_id: string | null;
  metadata: Record<string, unknown>;
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
  editor_html?: string | null;
  scene_script_id?: string | null;
  scene_script_summary?: string | null;
  narrator_input_source?: string | null;
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
  intervention_options?: string[];
  error: string | null;
  features: SimulationFeatures;
}

export interface SessionSummary {
  sim_id: string;
  status: SimStatus;
  premise: string;
  nodes_count: number;
  error?: string | null;
}

export interface BranchCompareResponse {
  sim_id: string;
  active_branch_id: string;
  branches: Record<string, BranchCompareSummary>;
}

export interface DualLoopRolloutCheck {
  name: string;
  status: "pass" | "warn" | "fail";
  required: boolean;
  detail: string;
}

export interface DualLoopCompareReport {
  sim_id: string;
  generated_at: string;
  active_branch_id: string;
  contract_version: string;
  legacy_path: {
    node_count: number;
    rendered_node_count: number;
    event_source: string;
    available: boolean;
  };
  dual_loop_path: {
    enabled: boolean;
    scene_script_node_count: number;
    narrator_input_v2_node_count: number;
    action_intent_count: number;
    intent_critique_count: number;
    critic_rejected_count: number;
    prompt_trace_count: number;
    reflection_note_count: number;
  };
  telemetry: {
    event_count: number;
    stage_counts: Record<string, number>;
  };
  rollout_readiness: {
    ready: boolean;
    checks: DualLoopRolloutCheck[];
    required_commands: string[];
  };
  rollback: {
    feature_flag: string;
    disable_value: string;
    runbook: string;
  };
}

export interface WikiIssue {
  level: "warning" | "error";
  path: string;
  message: string;
}

export interface WikiEntityInput {
  name: string;
  description: string;
  metadata?: Record<string, unknown>;
}

export interface WikiCharacterInput {
  id?: string;
  name: string;
  description: string;
  personality: string;
  goals: string[];
  status: string;
  metadata?: Record<string, unknown>;
}

export interface WikiSaveResponse {
  message: string;
  issues: WikiIssue[];
  world: WorldData;
}

export interface RouteDiagnostics {
  route_group: string;
  provider: string;
  model: string;
  calls: number;
  agents: string[];
  duration_ms: number;
  estimated_prompt_tokens: number;
  estimated_completion_tokens: number;
  estimated_cost_usd: number | null;
  fallbacks: number;
}

export interface SimulationDiagnostics {
  sim_id: string;
  status: SimStatus;
  active_branch_id: string;
  routing: Record<string, unknown>;
  memory: {
    total_entries: number;
    active_entries: number;
    archived_entries: number;
    summary_entries: number;
    event_entries: number;
    reflection_entries: number;
    latest_tick: number;
    vector_backend?: string;
    vector_backend_requested?: string;
    vector_backend_fallback_reason?: string | null;
  };
  llm: {
    total_calls: number;
    total_duration_ms: number;
    estimated_prompt_tokens: number;
    estimated_completion_tokens: number;
    estimated_cost_usd: number | null;
    routes: RouteDiagnostics[];
  };
  dual_loop: {
    enabled: boolean;
    contract_version: string;
    adapter_mode: string;
    scene_plan: ScenePlan | null;
    action_intents: ActionIntent[];
    intent_critiques: IntentCritique[];
    scene_script: SceneScript | null;
    prompt_traces: PromptTrace[];
  };
}

export interface SimulationInspector {
  sim_id: string;
  current_node_id: string | null;
  node_title: string | null;
  scene_plan: ScenePlan;
  scene_script: SceneScript;
  action_intents: ActionIntent[];
  intent_critiques: IntentCritique[];
  prompt_traces: PromptTrace[];
  summary: {
    prompt_trace_count: number;
    action_intent_count: number;
    critic_rejected_count: number;
    accepted_intent_count: number;
    rejected_intent_count: number;
  };
}

export type ExportArtifactKind =
  | "novel_txt"
  | "novel_markdown"
  | "novel_html"
  | "novel_docx"
  | "novel_pdf"
  | "world_settings_json"
  | "timeline_json"
  | "manifest_json";

export interface ExportManifestFile {
  kind: ExportArtifactKind;
  filename: string;
  mime_type: string;
}

export interface ExportData {
  sim_id: string;
  branch_id: string;
  generated_at: string;
  summary: {
    node_count: number;
    rendered_node_count: number;
    character_count: number;
    rule_count: number;
    faction_count: number;
    location_count: number;
  };
  manifest: {
    bundle_name: string;
    generated_at: string;
    sim_id: string;
    branch_id: string;
    files: ExportManifestFile[];
  };
  novel: string;
  markdown: string;
  html: string;
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
    branch_id?: string;
  }>;
}
