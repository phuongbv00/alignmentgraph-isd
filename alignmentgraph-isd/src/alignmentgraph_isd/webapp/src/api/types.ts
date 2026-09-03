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

/** One message as it stood in an agent's transcript. Mirrors
 *  `core/agentic/loop.py::serialize_messages`, which flattens the MIXED live
 *  transcript — plain dicts plus the model's own message objects — into this. */
export interface ContextMessage {
  /** Compaction has taken this turn OUT of the live context: the model no
   *  longer sees it and it is not counted in the window meter. Kept and shown
   *  because the tab answers "what was this agent shown", and a transcript
   *  reduced to what is still being sent answers that for the last call only. */
  compacted?: boolean
  role: string
  content: string
  name?: string
  /** Where a submitted artifact actually lives: an assistant turn that submits
   *  carries empty content and the whole artifact in its tool call. */
  tool_calls?: unknown[]
}

/** One context WITHOUT its transcript: what the live stream carries.
 *
 *  A loop republishes its context after every turn, so pushing the transcripts
 *  would re-send every one of them tens of times per run. The rows are the
 *  whole of the list view — who is speaking, in which phase, how much of the
 *  window they are using — and the transcript is fetched when a row is opened. */
export type AgentContextRow = Omit<AgentContext, 'messages' | 'tools'> & {
  messages?: ContextMessage[]
  tools?: AgentContext['tools']
  /** Messages so far. The list shows it moving while the agent is still going. */
  turns?: number
}

/** Everything one agent was shown. Published by the harness through `on_event`
 *  and stored as run state, never folded into the recorded trajectory: the
 *  judge reads that and the benchmark compares it across arms. */
export interface AgentContext {
  /** Stable identity of this conversation, from the harness
   *  (`core.memory.context_id`). A loop republishes its context after every
   *  turn and the republish REPLACES the snapshot before it; this is what
   *  "the same context" means, decided in one place so the server and the
   *  browser cannot drift from each other on it. */
  id: string
  agent: string
  phase: string
  /** Stage name, or `stage:SET-ID` for a Developer working one work set. */
  label: string
  /** Which regen attempt this was. A stage that came back empty is run again
   *  from a FRESH context, so attempt 2 is a different context, not more of
   *  the same one — and, since it starts a new message list, a different agent
   *  run with a row of its own.
   *
   *  Data, not a label: the rows are already in publication order, so the
   *  attempts of one stage read top to bottom without anything saying so. It
   *  was surfaced as a "retry #N" badge and that was worse than nothing —
   *  every reader who saw it had to work out whether something had gone
   *  wrong. */
  attempt?: number
  messages: ContextMessage[]
  /** The bound tool schemas. Under native tool calling these are half of what
   *  the model sees, so a context view without them shows half the context. */
  tools: { function?: { name?: string; description?: string; parameters?: unknown } }[]
  chars: number
  budget?: number
  /** The transcript as a true PARTITION, in tokens — the three sum to
   *  `total_tokens`, so a bar drawn from them cannot lie about what filled the
   *  window.
   *
   *  `system`   instructions and rules for the model.
   *  `messages` the conversation proper: user and assistant text.
   *  `tools`    tool calls and their results — the function names and
   *             arguments the model asked for, and the data that came back. */
  tokens?: { system: number; messages: number; tools: number }
  total_tokens?: number
  /** Tokens the transcript may occupy: the serving window minus what must be
   *  left for the answer. */
  token_budget?: number
  /** How many turns compaction has taken out of the live context so far. */
  compacted?: number
  /** The bound schemas. Real context, but not in the message list, so it sits
   *  BESIDE the partition rather than inside it. */
  schema_tokens?: number
  /** Whether the chars-per-token ratio behind these numbers came from the
   *  provider's own `prompt_tokens` yet, or is still the cold-start estimate. */
  ratio_measured?: boolean
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
  bloom_ok: boolean
  aligned: boolean
  /** Gone with C7 (2026-09-02): a rubric criterion is a field of the item that
   *  measures the objective, so this was true whenever `measured` was and
   *  never narrowed `aligned`. Optional so an archived run still parses. */
  evaluated?: boolean
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
  contexts_rev?: number
  replay?: boolean
}

/** What the UI shows for a selected artifact. One shape drives the inspector. */
export type Selection =
  | { kind: 'none' }
  | { kind: 'brief' }
  | { kind: 'graph-node'; id: string }
  | { kind: 'graph-edge'; id: string; edge: GraphEdge }
  // One row of the deep trajectory; carries every action it folded together.
  | { kind: 'action'; id: string; actions: DeepAction[] }
  | { kind: 'artifact'; id: string }
