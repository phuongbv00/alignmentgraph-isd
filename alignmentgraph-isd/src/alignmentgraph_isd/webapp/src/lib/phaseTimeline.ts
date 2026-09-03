import type { DeepAction } from '../api/types'

/**
 * Folding the deep trajectory into the run's STORY: a chronological sequence
 * of phase blocks — one per ADDIE stage — instead of a per-agent grid that
 * loses time.
 *
 * The spine is the run's own stage order (`phase_started`/`phase_finished`
 * bracket every stage), which makes three things legible that the grid hid:
 *
 *  - the stage order itself ("at time t, agent A did X");
 *  - the two tiers inside one stage: a stage that fans out dispatches work
 *    sets to Developers, which act under their own identity but inside their
 *    Designer's phase — so they fold into the SAME block, and the block names
 *    every agent that acted in it rather than only the last one.
 *
 * Overlapping blocks are still marked as one parallel group. The current
 * design never produces one — stages run in sequence and Developers run one
 * set at a time — but archived runs from the concurrent pipeline replay
 * through this same folding, so the bracket-driven grouping stays.
 *
 * Two altitudes: each block carries a story summary (model turns, work sets
 * dispatched, artifacts submitted, self-check rounds) AND the full action list
 * for the audit view — nothing is dropped, only demoted.
 *
 * Every stage is an act->observe tool loop (`core/agentic/`), so a "model call"
 * here is one TURN of that loop, and an artifact is written by a `submit` tool
 * call the harness accepted — never written by the harness on its behalf.
 */

export type BlockKind = 'generation' | 'aggregate'

export interface PhaseBlock {
  id: string
  phase: string
  kind: BlockKind
  /** Workflow position, from phase_started (1-based). */
  index: number
  total: number
  startedAt: string
  durationMs: number | null
  /** The agent that OWNS this block: the first to act in it, which is the
   *  stage's Designer — not the last, which after a fan-out is whichever
   *  Developer happened to finish the final set. '' for pure-harness blocks. */
  agent: string
  /** Every agent that acted in the block, in first-seen order: the Designer
   *  and any Developers it dispatched. Drives the filter chips, so a
   *  Developer is selectable instead of hidden behind its Designer. */
  agents: string[]

  modelCalls: number
  /** node_write op=add counts by node type. */
  writes: Record<string, number>
  edgesDrawn: number
  edgesReverified: number
  /** violation_count per self-check round, in order (e.g. [4, 1, 0]). */
  checkRounds: number[]
  repairs: number
  /** Recovery-action counts (retry, regen_empty_section, ...). */
  recoveries: Record<string, number>
  /** Graph reads/walks — audit detail, not story. */
  graphOps: number

  /** Work sets this stage dispatched to its Developers (fan-out), and their
   *  ids. Zero for a stage that does its own work and for the single arm,
   *  which has no Developer tier at all. */
  workSets: number
  workSetIds: string[]
  /** Residual cross-artifact violations routed to this block's family in the
   *  reconciliation pass, and which kinds. Routing only happens in graph
   *  mode — prose has nothing cross-family to route. */
  routedViolations: number
  routedViolationTypes: string[]

  /** Aggregate fields (kind === 'aggregate'); null/empty elsewhere. */
  schemaErrors: number | null
  /** The residual whole-graph audit (GraphAuditor), null until its event
   *  lands. Counts + the gapped relation ids only — the full per-relation
   *  detail stays in metadata.audit, this is a summary pointer to it. */
  auditGapCount: number | null
  auditGappedRelations: string[]
  auditReady: boolean | null

  /** Everything the block folded, for the audit expansion + inspector. */
  actions: DeepAction[]
  /** Non-null when this block overlapped another in time (fan-out). */
  parallelGroup: number | null
}

// Mirrors `_RECOVERY_ACTIONS` in core/trajectory.py. `agentic_gave_up` replaced
// `agentic_fallback` when the scripted rescue was removed (2026-09-01): a stage
// that ends without a valid artifact now leaves it to the deterministic repair
// net instead of having one written for it, so the two are not the same event
// under a new name and old runs must keep reading as what they were.
const RECOVERY_ACTIONS = new Set([
  'retry', 'regen_empty_section', 'agent_error', 'llm_error', 'salvage_truncated',
  'invalid_action', 'submit_rejected', 'submit_invalid_final', 'repeated_tool_call',
  'commit_invalid_section', 'agentic_gave_up', 'budget_exhausted',
  'tool_binding_unavailable', 'tool_call_markup_recovered',
  // Added 2026-09-04: these four were live in `_RECOVERY_ACTIONS` but missing
  // here, so `absorb()` fell through to `default:` and they were counted
  // NOWHERE on a phase card. `context_compacted` was the costly one — how
  // often each arm compacts is how the `agent_mode` axis reports its price,
  // and `single` (one context all run) reaches it far sooner than `multi`.
  'duplicate_submit', 'bare_artifact_wrapped', 'dropped_argument',
  'context_compacted',
  'agentic_fallback',
  // Two members of `_RECOVERY_ACTIONS` are deliberately NOT here: `repair`
  // has its own case in absorb(), and `repair_unfilled` can no longer be
  // emitted (no repair calls the model since 2026-09-03).
])

function blockKind(phase: string): BlockKind {
  if (phase === 'aggregate') return 'aggregate'
  return 'generation'
}

function newBlock(action: DeepAction, sequence: number): PhaseBlock {
  const context = action.context
  const phase = String(context.phase ?? '')
  return {
    id: `phase-${sequence}-${phase}`,
    phase,
    kind: blockKind(phase),
    index: Number(context.index ?? 0),
    total: Number(context.total ?? 0),
    startedAt: action.timestamp,
    durationMs: null,
    agent: '',
    modelCalls: 0,
    writes: {},
    edgesDrawn: 0,
    edgesReverified: 0,
    checkRounds: [],
    repairs: 0,
    recoveries: {},
    graphOps: 0,
    agents: [],
    workSets: 0,
    workSetIds: [],
    routedViolations: 0,
    routedViolationTypes: [],
    schemaErrors: null,
    auditGapCount: null,
    auditGappedRelations: [],
    auditReady: null,
    actions: [],
    parallelGroup: null,
  }
}

function absorb(block: PhaseBlock, action: DeepAction): void {
  block.actions.push(action)
  if (action.agent && !block.agents.includes(action.agent)) block.agents.push(action.agent)
  const context = action.context
  switch (action.action) {
    case 'llm_call':
      block.modelCalls += 1
      return
    case 'agent_step':
      // First writer wins: the Designer opens the stage, its Developers step
      // afterwards, and the card must stay named after the stage's owner.
      if (action.agent) block.agent ||= action.agent
      return
    case 'node_write':
      if (context.op === 'add') {
        const type = String(context.node_type ?? 'node')
        block.writes[type] = (block.writes[type] ?? 0) + 1
      }
      return
    case 'edge_write':
      if (context.op === 'refresh') block.edgesReverified += 1
      else block.edgesDrawn += 1
      return
    case 'check':
      block.checkRounds.push(Number(context.violation_count ?? 0))
      if (action.agent && block.kind === 'generation') block.agent ||= action.agent
      return
    case 'repair':
      block.repairs += 1
      return
    case 'validate':
      block.schemaErrors = Number(context.error_count ?? 0)
      if (action.agent && !block.agent) block.agent = action.agent
      return
    case 'audit':
      block.auditGapCount = Number(context.residual_gap_count ?? 0)
      block.auditGappedRelations = (context.gapped_relations as string[] | undefined) ?? []
      block.auditReady = Boolean(context.ready_to_aggregate)
      return
    case 'doc_write': {
      // The prose arm's counterpart of node_write: without it a prose block
      // would report model turns and nothing produced.
      const key = String(context.key ?? 'document')
      block.writes[key] = (block.writes[key] ?? 0) + 1
      return
    }
    case 'dev_plan':
      block.workSets += Number(context.set_count ?? 0)
      block.workSetIds.push(
        ...((context.sets as { set_id?: string }[] | undefined) ?? [])
          .map((set) => String(set.set_id ?? ''))
          .filter(Boolean),
      )
      return
    case 'reconcile':
      block.routedViolations += Number(context.routed ?? 0)
      block.routedViolationTypes.push(
        ...((context.violation_types as string[] | undefined) ?? []),
      )
      return
    case 'node_read':
    case 'edge_read':
    case 'edge_walk':
      block.graphOps += 1
      return
    default:
      if (RECOVERY_ACTIONS.has(action.action)) {
        block.recoveries[action.action] = (block.recoveries[action.action] ?? 0) + 1
      }
  }
}

export function buildPhaseTimeline(actions: DeepAction[]): PhaseBlock[] {
  const blocks: PhaseBlock[] = []
  const open = new Map<string, PhaseBlock>()
  let parallelGroups = 0

  for (const action of actions) {
    const phase = String(action.context.phase ?? '')

    if (action.action === 'phase_started') {
      const block = newBlock(action, blocks.length)
      // Overlap with anything already open marks a fan-out; every member of
      // the overlap shares one group id so the renderer can lay them side by
      // side.
      if (open.size > 0) {
        let group: number | null = null
        for (const other of open.values()) group = other.parallelGroup ?? group
        if (group === null) group = ++parallelGroups
        block.parallelGroup = group
        for (const other of open.values()) other.parallelGroup = group
      }
      open.set(phase, block)
      blocks.push(block)
      continue
    }

    if (action.action === 'phase_finished') {
      const block = open.get(phase)
      if (block) {
        block.durationMs = Number(action.context.duration_ms ?? 0)
        open.delete(phase)
      }
      continue
    }

    // Thread-local phase attribution routes interleaved concurrent work to
    // the right open block. Anything outside a phase (nothing today) folds
    // into the most recently opened block rather than vanishing.
    const block = open.get(phase) ?? [...open.values()].pop() ?? blocks[blocks.length - 1]
    if (block) absorb(block, action)
  }

  return blocks
}

/** Distinct specialist agents in block order, for the filter chips.
 *  Generation blocks only: the aggregator and the harness are connective
 *  tissue, not something to filter by. */
export function timelineAgents(blocks: PhaseBlock[]): string[] {
  return [...new Set(
    blocks.filter((block) => block.kind === 'generation')
      .flatMap((block) => block.agents)
      .filter(Boolean),
  )]
}

/** "5× objective, 1× course_goal" — top types, capped so the line stays short. */
export function writesSummary(writes: Record<string, number>, cap = 3): string {
  const entries = Object.entries(writes).sort((a, b) => b[1] - a[1])
  const shown = entries.slice(0, cap).map(([type, count]) => `${count}× ${type}`)
  const rest = entries.length - cap
  return shown.join(', ') + (rest > 0 ? ` +${rest} more` : '')
}

// ── phase vocabulary ─────────────────────────────────────────────────────────

// Phase names are the agentic stage names (`STEPS` in
// core/agentic/specialists.py), plus the final aggregate. The single arm runs
// one ReAct loop over all of them, so it reports a single `design` phase — the
// absence of per-stage brackets there IS the decomposition axis, not a gap in
// the record; what it worked on, and in what order, is in
// `metadata.autonomy.design`.
// Deliberately no ADDIE-phase prefix (no "Design —", "Development —"): a stage
// designs AND develops its own concern before handing off, so a phase-name
// prefix would claim a sequencing that isn't real. `aggregate` is the one
// exception: it genuinely files everything into the ADDIE-shaped output.
const PHASE_LABELS: Record<string, string> = {
  analysis: 'Needs & context analysis',
  outcomes: 'Goals & objectives',
  assessment: 'Assessment — plan, tasks & rubrics',
  activities: 'Learning activities',
  content: 'Content & materials',
  implementation: 'Delivery plan',
  design: 'Whole design (one agent, one loop)',
  reconcile: 'Reconciling cross-artifact violations',
  aggregate: 'Assembling the ADDIE output',
}

export function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase] ?? humanise(phase)
}

function humanise(text: string): string {
  const spaced = text.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

// ── agent colours ────────────────────────────────────────────────────────────

/** One fixed hue per agent so every panel speaks the same colour. A Developer
 *  shares the hue of the Designer that dispatched it — the fan-out is the same
 *  concern at a finer grain, and the pill already spells out which tier acted.
 *  There is no RubricDeveloper: rubrics are written by the Assessment
 *  Developer that wrote the items they mark. */
const AGENT_HUES: Record<string, { bg: string; fg: string; dot: string }> = {
  NeedsAnalystAgent: { bg: '#fef3c7', fg: '#92400e', dot: '#f59e0b' },
  OutcomeDesignerAgent: { bg: '#ede9fe', fg: '#5b21b6', dot: '#8b5cf6' },
  AssessmentDesignerAgent: { bg: '#dbeafe', fg: '#1e40af', dot: '#3b82f6' },
  AssessmentDeveloperAgent: { bg: '#dbeafe', fg: '#1e40af', dot: '#3b82f6' },
  ActivityDesignerAgent: { bg: '#dcfce7', fg: '#166534', dot: '#22c55e' },
  ActivityDeveloperAgent: { bg: '#dcfce7', fg: '#166534', dot: '#22c55e' },
  ContentDesignerAgent: { bg: '#ffedd5', fg: '#9a3412', dot: '#f97316' },
  MaterialDeveloperAgent: { bg: '#ffedd5', fg: '#9a3412', dot: '#f97316' },
  ImplementationPlannerAgent: { bg: '#cffafe', fg: '#155e75', dot: '#06b6d4' },
  SingleDesignerAgent: { bg: '#ede9fe', fg: '#5b21b6', dot: '#8b5cf6' },
  WorkflowOrchestrator: { bg: '#f1f5f9', fg: '#334155', dot: '#64748b' },
  ADDIEOutputAggregator: { bg: '#f1f5f9', fg: '#334155', dot: '#64748b' },
}

const FALLBACK_HUE = { bg: '#f1f5f9', fg: '#334155', dot: '#94a3b8' }

export function agentHue(agent: string): { bg: string; fg: string; dot: string } {
  return AGENT_HUES[agent] ?? FALLBACK_HUE
}

/** "OutcomeDesignerAgent" → "OutcomeDesigner" — pills stay short. The
 *  Designer/Developer distinction survives the trim, which is the one thing a
 *  reader must not lose: it says which tier acted. */
export function agentShortName(agent: string): string {
  return agent.replace(/Agent$/, '')
}
