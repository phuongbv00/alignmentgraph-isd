import type { DeepAction } from '../api/types'

/**
 * Folding the deep trajectory into the run's STORY: a chronological sequence
 * of phase blocks — one per workflow node execution — instead of a per-agent
 * grid that loses time.
 *
 * The spine is the workflow's own phase order (`phase_started`/`phase_finished`
 * bracket every node), which makes three things legible that the grid hid:
 *
 *  - the pipeline order itself ("at time t, agent A did X");
 *  - genuine concurrency: content/rubric fan out on separate LangGraph worker
 *    threads, and their actions interleave. Every action carries its own
 *    `context.phase` (thread-local), so interleaved work still folds into the
 *    right block; overlapping blocks are marked as one parallel group.
 *
 * Two altitudes: each block carries a story summary (model calls, artifacts
 * written, self-check rounds) AND the full action list for the audit view —
 * nothing is dropped, only demoted.
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
  /** The specialist who acted in this block ('' for pure-harness blocks). */
  agent: string

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

const RECOVERY_ACTIONS = new Set([
  'retry', 'regen_empty_section', 'agent_error', 'llm_error', 'salvage_truncated',
  'invalid_action', 'submit_rejected', 'submit_invalid_final', 'repeated_tool_call',
  'commit_invalid_section', 'agentic_fallback',
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
  const context = action.context
  switch (action.action) {
    case 'llm_call':
      block.modelCalls += 1
      return
    case 'agent_step':
      if (action.agent) block.agent = action.agent
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
      .map((block) => block.agent)
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

// Phase names are the workflow's node names (core/workflow.py): one per
// Designer, and the final aggregate. `monolithic_designer` is the ablation's
// single-agent arm.
// Deliberately no ADDIE-phase prefix (no "Design —", "Development —"): the
// workflow does not run phase-by-phase — each specialist designs AND
// develops its own concern, then hands off — so a phase-name prefix would
// claim a sequencing that isn't real. `aggregate` is the one exception: it
// genuinely files everything into the ADDIE-shaped output artifact.
const PHASE_LABELS: Record<string, string> = {
  outcome_designer: 'Goals & objectives',
  assessment_designer: 'Assessment — plan & tasks',
  activity_designer: 'Learning activities',
  content_designer: 'Content & materials',
  rubric_designer: 'Rubrics',
  implementation_planner: 'Delivery plan',
  monolithic_designer: 'All artifacts (single agent)',
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

/** One fixed hue per specialist so every panel speaks the same colour. */
const AGENT_HUES: Record<string, { bg: string; fg: string; dot: string }> = {
  OutcomeDesignerAgent: { bg: '#ede9fe', fg: '#5b21b6', dot: '#8b5cf6' },
  AssessmentDesignerAgent: { bg: '#dbeafe', fg: '#1e40af', dot: '#3b82f6' },
  ActivityDesignerAgent: { bg: '#dcfce7', fg: '#166534', dot: '#22c55e' },
  ContentDesignerAgent: { bg: '#ffedd5', fg: '#9a3412', dot: '#f97316' },
  RubricDesignerAgent: { bg: '#fce7f3', fg: '#9d174d', dot: '#ec4899' },
  ImplementationPlannerAgent: { bg: '#cffafe', fg: '#155e75', dot: '#06b6d4' },
  SingleDesignerAgent: { bg: '#ede9fe', fg: '#5b21b6', dot: '#8b5cf6' },
  ADDIEOutputAggregator: { bg: '#f1f5f9', fg: '#334155', dot: '#64748b' },
}

const FALLBACK_HUE = { bg: '#f1f5f9', fg: '#334155', dot: '#94a3b8' }

export function agentHue(agent: string): { bg: string; fg: string; dot: string } {
  if (AGENT_HUES[agent]) return AGENT_HUES[agent]
  // Agentic-arm personas ("AgenticOutcomeDesigner") share their scripted
  // counterpart's colour.
  for (const [name, hue] of Object.entries(AGENT_HUES)) {
    const stem = name.replace(/Agent$/, '')
    if (agent.includes(stem.replace('Designer', ''))) return hue
  }
  return FALLBACK_HUE
}

/** "OutcomeDesignerAgent" → "OutcomeDesigner" — pills stay short. */
export function agentShortName(agent: string): string {
  return agent.replace(/Agent$/, '')
}
