// Wire types, mirroring server/schemas.py.

export interface Health {
  llm_configured: boolean
  model_name: string
  /** Why the model is unusable, when it is. Shown verbatim. */
  model_error: string
  active_runs: number
  max_concurrent_runs: number
}

export interface LLMConnection {
  id: string
  name: string
  base_url: string
  /** The key itself is never sent to the browser — only whether one is set. */
  has_api_key: boolean
  model_name: string
  temperature: number | null
  /** The completion cap, which is also the transcript budget's reserve. */
  max_tokens: number | null
  /** The window the endpoint serves, in tokens. */
  context_window: number | null
  /** Reasoning ceiling in tokens: null = the server's posture, 0 = off, N = at most N. */
  thinking_budget: number | null
  is_active: boolean
  updated_at: string | null
}

/** Every connection endpoint answers with this, so the dialog has one source of state. */
export interface LLMConnections {
  connections: LLMConnection[]
  active_id: string
  /** Why the active connection is unusable, if it is. */
  error: string
}

export interface LLMConnectionInput {
  name: string
  base_url: string
  /** Omit to keep the stored key; send "" to clear it. */
  api_key?: string
  /** Empty until one is picked from the endpoint's own list. */
  model_name: string
  /** Sent on every save: a null that is actually sent clears the stored value. */
  temperature: number | null
  max_tokens: number | null
  context_window: number | null
  thinking_budget: number | null
}

export interface ModelList {
  models: string[]
  /** Why the list is empty, if it is. */
  error: string
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

/** The two ablation axes, as the server spells them (`config.py`). */
export type AgentMode = 'single' | 'multi'
/** How much of the planned scale a run writes out. Not an ablation axis. */
export type DevelopmentMode = 'sample' | 'full'
export type ContextMode = 'prose' | 'graph'

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
  // Not statistics: the ablation ARM the run was executed under. They ride in
  // `stats` because the run row has no column for them and the demo database
  // has no migrations — see server/events.py::RunState. Absent on a run
  // recorded before this existed, which is why they are optional.
  agent_mode?: AgentMode
  context_mode?: ContextMode
  // Beside the arm for the same reason, and optional for the same reason.
  development_mode?: DevelopmentMode
  /** Present only when a run asked for more than one; wall time only. */
  fanout_workers?: number
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
  /** An earlier `read_alignment_state` result that a later one replaced: the
   *  live context — and the window meter — holds a one-line stub in its place,
   *  which is what `content` is. `original_content` is what the agent was
   *  actually shown at the time, kept because that is what the tab answers. */
  superseded?: boolean
  original_content?: string
  /** The model's reasoning channel, when the endpoint splits one out of the
   *  answer. Shown because the tab answers what this agent did, and thinking
   *  that goes unrecorded answers it for half the turn — but never sent back
   *  to the model, and never counted in the window meter, which measures what
   *  IS sent. Dimmed for exactly that reason. */
  reasoning?: string
  role: string
  content: string
  name?: string
  /** Where a submitted artifact actually lives: an assistant turn that submits
   *  carries empty content and the whole artifact in its tool call. */
  tool_calls?: unknown[]
}

/** One violation, followed from its first sighting to its outcome.
 *
 *  Kept by the run itself (`core/memory.py`) rather than reconstructed from
 *  the trajectory, and the sole owner of the question: `metadata.audit` used
 *  to publish the graph arm's residual beside it, as five of these eight
 *  fields, and no longer does. */
export interface Finding {
  /** Built from the SUBJECT of the finding (type + node + the metadata that
   *  says which one it is), never from the evidence behind it: a bloom
   *  mismatch's `item_ids` grows as Developers commit while the problem
   *  stands, and a key that moved with it would report the finding closed and
   *  a new one opened. */
  key: string
  type: string
  node_id: string
  severity: string
  /** One finding can be reported more than one way — a relation's establisher
   *  and the coverage sweep say the same thing differently — so both wordings
   *  are kept rather than one being lost to the other. */
  messages: string[]
  repair_hint: string
  metadata: Record<string, unknown>
  target_designer: string
  first_phase: string
  first_round: number
  last_round: number
  sightings: number
  /** Rounds in which it actually reached a model. */
  shown_to_agent: number
  outcome: 'open' | 'repaired_by_harness' | 'repaired_by_agent'
  /** Only meaningful while open, and the whole point of the ledger: WHY it is
   *  still here. `converged` is a result about the model; `budget` is a
   *  parameter we chose. Reporting them merged would be a wrong claim. */
  open_reason: string
  /** The deterministic net is DESIGNED never to touch this type. Orthogonal to
   *  `outcome`, not a value of it — "report-only AND repaired by the agent" is
   *  reachable, and is the evidence that the agent tier does work the net
   *  cannot. */
  report_only: boolean
  repaired_by: string
  repaired_at_round: number
  converged_at_round: number
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
   *  (`core.memory.new_agent_run_id`). A loop republishes its context after every
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
   *  left for the answer. This is the meter's denominator — NOT the window,
   *  which is why the two below travel with it. */
  token_budget?: number
  /** The configured serving window, and the share of it held back for the
   *  reply. 0 when the connection does not say, in which case the budget is
   *  the harness's own constant. */
  token_window?: number
  token_reserve?: number
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
}

// ── the alignment graph ──────────────────────────────────────────────────────

/** The display fields below are decided once, by the harness (`viz.py`), and
 *  read here — not worked out again in TypeScript. That is the 2026-09-11
 *  arrangement: the payload carries every display SEMANTIC, this app keeps
 *  only colour and shape. They are optional because a `graph.json` archived
 *  before they existed still has to render; the server upgrades such a payload
 *  on read, so the `??` fallbacks below are for a raw file, not the normal path.
 *
 *  `data` is present on the full view only; the wire (light) view omits it —
 *  which works precisely because nothing here draws from `data`. */
export interface GraphNode {
  id: string
  type: string
  data?: Record<string, any>
  /** Element: the item id it carries (`objective:LO-01` -> `LO-01`).
   *  Section: its type, because a section node IS its type. */
  label?: string
  kind?: 'element' | 'section'
  /** The one identifying line for a non-objective node (an activity's name, a
   *  material's title). Shipped so no renderer has to dig through `data`. */
  detail?: string
  /** Objectives only: the Bloom level. */
  level?: string
  repaired?: boolean
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
  /** Composed by the harness. It used to be composed HERE and, separately, in
   *  the inspector — which dropped the `scaffold` prefix, so selecting a
   *  `narrates` edge from a node's relation list matched nothing on canvas. */
  id?: string
  /** Which toggle shows it. From `REGISTRY`, not from the id's first letter. */
  layer?: 'alignment' | 'provenance' | 'scaffolding'
  tier?: 'core' | 'secondary' | ''
  /** An `assessed_by`/`practiced_by` edge whose objective fails ITS OWN Bloom
   *  check — C2 judged on the assessment rule, C3 on the activity rule. */
  invalid?: boolean
  invalid_reason?: '' | 'bloom_assessment' | 'bloom_activity'
}

/** One leg of the constructive-alignment triad, as the harness declares it.
 *  Every word comes from `alignment.REGISTRY`: `verb` is the relation's own
 *  `edge_type` (`assessed_by`) and `label` its sentence. A leg IS a core
 *  relation seen from the objective, so there is nothing to name here. */
export interface AlignmentLeg {
  relation_id: string
  verb: string
  label: string
  ok: boolean
}

/** A legend row as MEANING. The colour or shape for `key` is this app's to
 *  choose; the wording is not. */
export interface LegendEntry {
  key: string
  label: string
}

export interface ObjectiveAlignment {
  /** One scalar per leg, named by the relation's own verb (2026-09-14 —
   *  they were `measured`/`supported`/`prepares`, a third set of names for
   *  C2/C3/C4). Optional because an archived dump carries the old three; read
   *  `legs` instead, which the server backfills either way. */
  assessed_by?: boolean
  practiced_by?: boolean
  prepares_for?: boolean
  /** The pre-2026-09-14 names, present on an archived payload only. */
  measured?: boolean
  supported?: boolean
  prepares?: boolean
  /** The CONJUNCTION of the two below, with a `null` counting as no
   *  complaint. NOT part of `aligned` since 2026-09-10: Bloom is a content
   *  condition, and `aligned` is the structural triad. */
  bloom_ok: boolean
  /** TRI-STATE: true held, false violated, `null` NOT CHECKED — the rule has
   *  nothing to judge against (no C2/C3 edge) or the objective's `level` is
   *  outside Bloom's six. Read `=== false` for a failure and never `!x`: a
   *  null rendered as a pass drew a green "assessed at its own Bloom level"
   *  beside a red C2 leg on an objective no item assessed at all.
   *  Optional so an archived run still renders. */
  bloom_assessment_ok?: boolean | null
  bloom_activity_ok?: boolean | null
  /** The checks' own messages, verbatim: the level targeted, the level
   *  actually reached, and the field to edit. */
  bloom_notes?: string[]
  /** The constructive-alignment triad closed on this objective:
   *  `measured && supported && prepares`. An archived run computed it as
   *  `measured && supported && bloom_ok` instead, so the value is not
   *  comparable across the 2026-09-10 change. */
  aligned: boolean
  /** Gone with C7 (2026-09-02): a rubric criterion is a field of the item that
   *  measures the objective, so this was true whenever `measured` was and
   *  never narrowed `aligned`. Optional so an archived run still parses. */
  evaluated?: boolean
  /** The legs as an ORDERED list, which is what `aligned` is derived from.
   *  Render these rather than the booleans above: adding a leg (C4, 2026-09-10)
   *  used to mean editing four places that could disagree. */
  legs?: AlignmentLeg[]
}

export interface RelationCoverage {
  /** The relation's canonical wording, from `alignment.REGISTRY`. The one
   *  place a C/P relation is named for a reader. */
  label: string
  mechanism: string
  /** 'core' (C2-C4) | 'secondary' (P1-P14). Shipped all along and simply not
   *  declared here, which is why edges used to guess it from the id prefix. */
  tier?: 'core' | 'secondary'
  coverage: number
  uncovered: string[]
}

export interface AlignmentGraphPayload {
  nodes: GraphNode[]
  edges: GraphEdge[]
  objective_alignment: Record<string, ObjectiveAlignment>
  /** `node_id -> violation types`, for EVERY node type — the one signal
   *  that covers an activity linked to no objective or a material whose
   *  module does not exist. Types only: the messages are in the ledger. */
  node_violations?: Record<string, string[]>
  relation_coverage: Record<string, RelationCoverage>
  /** What each colour and fill MEANS, shipped with the graph it explains, so
   *  the two renderers cannot drift — they had: this app's legend listed six
   *  node rows to the DOT export's two, and never mentioned the triad legs at
   *  all, so the green fill it explained could not be traced to its cause. */
  legend?: { edges: LegendEntry[]; nodes: LegendEntry[] }
  /** Bumped when the display fields change shape; absent on a payload written
   *  before they existed. */
  schema_version?: number
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

/** One fan-out unit: the slice of work ONE Developer call was asked for.
 *  `payload` is family-shaped — an instrument hint, a content module, a block
 *  theme, the count it was asked for — which is the half the `dev_plan` event
 *  summary does not carry. */
export interface WorkSet {
  set_id: string
  objectives: string[]
  pairs: string[][]
  payload: Record<string, unknown>
  source: string
  /** 1-based position in its plan, and the first half of every id its
   *  Developer's artifacts commit under (`AT-0203` = set 2, artifact 3). */
  ordinal: number
}

/** One family's division into work sets, as its Designer decided it.
 *  `round` is 0 for the first division and 1+ for a plan made in answer to
 *  violations its Developers left. */
export interface PlanRecord {
  stage: string
  family: string
  /** 'llm' when the Designer's own dev plan was used, 'fallback' when it was
   *  absent or unusable, 'deterministic' for a family with no plan step. */
  source: string
  round: number
  answers: string[]
  work_sets: WorkSet[]
  stats: Record<string, number | boolean>
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
