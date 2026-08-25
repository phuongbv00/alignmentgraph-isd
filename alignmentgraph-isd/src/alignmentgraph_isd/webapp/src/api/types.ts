// Wire types, mirroring server/schemas.py.

export interface Health {
  llm_configured: boolean
  model_name: string
  /** Why the model is unusable, when it is. Shown verbatim. */
  model_error: string
  active_runs: number
  max_concurrent_runs: number
}

export interface LLMSettings {
  model_name: string
  api_spec: string
  base_url: string
  /** The key itself is never sent to the browser — only whether one is set. */
  has_api_key: boolean
  temperature: number | null
  max_tokens: number | null
  /** Where the value in effect came from. */
  source: 'database' | 'environment' | 'none'
  /** Why it is unusable, if it is. */
  error: string
}

export interface LLMSettingsInput {
  model_name: string
  api_spec: string
  base_url: string
  /** Omit to keep the stored key; send "" to clear it. */
  api_key?: string
  temperature: number | null
  max_tokens: number | null
}

export interface BriefPreview {
  id: string
  title: string
  domain: string
  difficulty: string
  duration: string
  target_audience: string
  user_message: string
  learning_goals: string[]
  learning_goals_total: number
  context_filled: number
  context_total: number
  constraints_filled: number
  constraints_total: number
  is_runnable: boolean
}

export type RunStatus = 'running' | 'cancelling' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted'

export interface RunStats {
  node_count?: number
  edge_count?: number
  objective_count?: number
  aligned_objective_count?: number
  llm_calls?: number
  token_usage?: { prompt_tokens?: number; completion_tokens?: number }
  agent_steps?: number
  check_rounds?: number
  repair_events?: number
  duration_seconds?: number
  event_count?: number
  graph_rev?: number
  model_name?: string
}

export interface RunSummary {
  id: string
  status: RunStatus
  error: string
  model_name: string
  stats: RunStats
  created_at?: string
  started_at?: string
  finished_at?: string
}

export interface ProgramSummary {
  id: string
  title: string
  source: string
  created_at: string
  updated_at: string
  /** Null while the brief is still a draft being built through the conversation. */
  brief_committed_at: string | null
  brief_preview: BriefPreview
  latest_run: RunSummary | null
}

export interface Message {
  id: number | null
  seq: number
  role: 'user' | 'assistant'
  content: string
  payload: {
    brief_patch?: Record<string, unknown>
    missing_fields?: string[]
    ready?: boolean
    warnings?: string[]
  }
  created_at?: string
}

export type Brief = Record<string, any>

export interface ProgramDetail {
  program: ProgramSummary
  brief: Brief
  brief_preview: BriefPreview
  messages: Message[]
  missing_fields: string[]
  runs: RunSummary[]
}

export interface PlanTurn {
  user_message: Message
  assistant_message: Message
  brief: Brief
  brief_preview: BriefPreview
  missing_fields: string[]
  ready: boolean
  warnings: string[]
  brief_committed_at: string | null
}

export interface BriefResponse {
  brief: Brief
  brief_preview: BriefPreview
  missing_fields: string[]
  warnings: string[]
  brief_committed_at: string | null
}

export interface RunDetail {
  run: RunSummary
  stats: RunStats
  brief_preview: BriefPreview
  graph_available: boolean
}

// ── the alignment graph ──────────────────────────────────────────────────────

/** Present on the full view only; the wire (light) view omits `data`. */
export interface GraphNode {
  id: string
  type: string
  data?: Record<string, any>
}

export interface GraphEdge {
  type: string
  source: string
  target: string
  evidence: string
  rationale: string
  relation_id: string
  /** How the edge was established: 'id' | 'type' | 'provenance', or '' for
   *  the internal scaffolding edges the DOT view also drops. */
  established_by: string
}

export interface ObjectiveAlignment {
  measured: boolean
  supported: boolean
  evaluated: boolean
  bloom_ok: boolean
  aligned: boolean
}

export interface RelationCoverage {
  label: string
  mechanism: string
  coverage: number
  uncovered: string[]
}

export interface AlignmentGraphPayload {
  nodes: GraphNode[]
  edges: GraphEdge[]
  objective_alignment: Record<string, ObjectiveAlignment>
  relation_coverage: Record<string, RelationCoverage>
  metadata: {
    design_brief_id?: string
    generated_at?: string
    node_count?: number
    edge_count?: number
    node_counts_by_type?: Record<string, number>
    edge_counts_by_type?: Record<string, number>
  }
}

// ── the run event stream ─────────────────────────────────────────────────────

export type EventKind =
  /** One entry of the deep trajectory; its payload is a `DeepAction`. */
  | 'action'
  | 'run_started'
  | 'phase_started'
  | 'phase_finished'
  | 'llm_started'
  | 'llm_finished'
  | 'agent_step'
  | 'node_edit'
  | 'llm_call'
  | 'validation_event'
  | 'check_event'
  | 'repair_event'
  | 'retrieval_event'
  | 'run_cancelling'
  | 'run_finished'
  | 'run_failed'
  | 'run_cancelled'

export interface RunEvent {
  seq: number
  kind: EventKind
  ts: string
  payload: Record<string, any>
}

/**
 * One entry of the deep trajectory: something an agent actually did.
 *
 * All action-specific details live in `context`. This leaves a stable envelope
 * for concurrent writers: time, responsible agent, action, then its details.
 */
export interface DeepAction {
  timestamp: string
  /** The agent that did it; empty for work the harness did outside an agent. */
  agent: string
  action: string
  context: Record<string, any>
}

export interface DeepTrajectory {
  format: 'deep'
  actions: DeepAction[]
  summary: {
    action_count: number
    by_action: Record<string, number>
    by_agent: Record<string, Record<string, number>>
    agents: string[]
    latency_ms: number
  }
}

export interface HelloPayload {
  run_id: string
  program_id: string
  status: RunStatus
  error: string
  model_name: string
  stats: RunStats
  graph_rev: number
  replay?: boolean
}

/** What the UI shows for a selected artifact. One shape drives the inspector. */
export type Selection =
  | { kind: 'none' }
  | { kind: 'brief' }
  | { kind: 'graph-node'; id: string }
  | { kind: 'graph-edge'; id: string; edge: GraphEdge }
  // The whole group the timeline row folded together — a model call carries
  // its started/finished pair, which is where the full prompt and reply are.
  | { kind: 'event'; id: string; events: RunEvent[] }
  // One row of the deep trajectory; carries every action it folded together.
  | { kind: 'action'; id: string; actions: DeepAction[] }
  | { kind: 'artifact'; id: string }
