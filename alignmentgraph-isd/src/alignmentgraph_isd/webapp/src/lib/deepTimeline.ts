import type { DeepAction } from '../api/types'

/**
 * Turning the deep trajectory into something a person can read.
 *
 * A run logs well over a thousand actions, most of them graph reads. Listed one
 * per row that is not a trajectory, it is a wall. So the log is folded twice:
 *
 *  1. **Runs of the same kind of work collapse.** Forty consecutive lookups by
 *     one agent become "read the graph 40×", expandable. This is where almost
 *     all the volume goes.
 *  2. **Rows group under the agent that performed them.** The question the view
 *     has to answer is "what did this agent do", and that only reads as an
 *     answer when the agent's work is in one place.
 *
 * What deliberately never collapses is the work that carries meaning on its
 * own: a model call, an alignment edge being drawn, a verification round, a
 * repair. Those are the story; the reads are the machinery.
 */

export type WorkKind =
  | 'read'      // looked at the graph
  | 'walk'      // followed relations
  | 'write'     // wrote nodes
  | 'link'      // drew alignment edges
  | 'model'     // called the model
  | 'step'      // recorded a step of its own
  | 'verify'
  | 'repair'
  | 'validate'
  | 'retrieval'
  | 'error'
  | 'phase'
  | 'other'

export interface DeepRow {
  id: string
  seq: number
  kind: WorkKind
  title: string
  detail: string
  actions: DeepAction[]
  /** Collapsed runs show how many were folded together. */
  count: number
  tone?: 'good' | 'warn' | 'bad'
}

export interface AgentGroup {
  id: string
  actor: string
  phase: string
  rows: DeepRow[]
  /** Headline counts for the group, so it reads without expanding. */
  tally: Partial<Record<WorkKind, number>>
  elapsedMs: number
}

const KIND_OF: Record<string, WorkKind> = {
  node_read: 'read',
  edge_read: 'read',
  edge_walk: 'walk',
  node_write: 'write',
  edge_write: 'link',
  llm_call: 'model',
  agent_step: 'step',
  verify: 'verify',
  repair: 'repair',
  validate: 'validate',
  retrieval: 'retrieval',
  retrieval_query: 'retrieval',
  agent_error: 'error',
  regen: 'warn' as WorkKind,
  phase_started: 'phase',
  phase_finished: 'phase',
}

/** Kinds worth a row each — collapsing them would hide the run's actual story. */
const NEVER_COLLAPSE: ReadonlySet<WorkKind> = new Set<WorkKind>([
  'model', 'verify', 'repair', 'validate', 'error', 'step', 'retrieval',
])

export function workKind(action: DeepAction): WorkKind {
  if (action.kind === 'regen') return 'error'
  return KIND_OF[action.kind] ?? 'other'
}

export function groupDeepActions(actions: DeepAction[]): AgentGroup[] {
  const groups: AgentGroup[] = []
  const ordered = [...actions].sort((a, b) => a.seq - b.seq)

  for (const action of ordered) {
    // Phase markers define the boundaries; they are not work in themselves.
    if (action.kind === 'phase_started' || action.kind === 'phase_finished') continue

    const actor = action.actor || '(harness)'
    let group = groups[groups.length - 1]
    if (!group || group.actor !== actor || group.phase !== action.phase) {
      group = {
        id: `${action.phase}-${actor}-${action.seq}`,
        actor,
        phase: action.phase,
        rows: [],
        tally: {},
        elapsedMs: action.elapsed_ms,
      }
      groups.push(group)
    }
    group.elapsedMs = action.elapsed_ms

    const kind = workKind(action)
    group.tally[kind] = (group.tally[kind] ?? 0) + 1

    const last = group.rows[group.rows.length - 1]
    if (last && last.kind === kind && !NEVER_COLLAPSE.has(kind)) {
      last.actions.push(action)
      last.count = last.actions.length
      last.title = titleFor(kind, last.actions)
      last.detail = detailFor(kind, last.actions)
      continue
    }

    group.rows.push({
      id: `a-${action.seq}`,
      seq: action.seq,
      kind,
      title: titleFor(kind, [action]),
      detail: detailFor(kind, [action]),
      actions: [action],
      count: 1,
      tone: toneFor(kind, action),
    })
  }

  return groups
}

function titleFor(kind: WorkKind, actions: DeepAction[]): string {
  const first = actions[0]
  const n = actions.length
  switch (kind) {
    case 'read':
      return n === 1 ? 'Read the graph' : `Read the graph ${n}×`
    case 'walk':
      return n === 1 ? 'Followed relations' : `Followed relations ${n}×`
    case 'write':
      return n === 1 ? `Wrote ${first.node_id}` : `Wrote ${n} nodes`
    case 'link':
      return n === 1
        ? `Linked ${first.source} → ${first.target}`
        : `Drew ${n} alignment edges`
    case 'model':
      return 'Called the model'
    case 'step':
      return String(first.action ?? 'Step')
    case 'verify':
      return `Verification round ${first.round ?? ''}`.trim()
    case 'repair':
      return `Repaired ${first.violation_type} on ${first.node_id}`
    case 'validate':
      return `Validated ${first.scope}`
    case 'retrieval':
      if (first.kind === 'retrieval_query') {
        return n === 1
          ? `Queried ${first.retrieval_agent}`
          : `Queried ${n} sources`
      }
      return `Retrieval: ${first.decision}`
    case 'error':
      return first.kind === 'regen'
        ? `Regenerated (attempt ${first.attempt})`
        : 'Agent failed'
    default:
      return first.kind
  }
}

function detailFor(kind: WorkKind, actions: DeepAction[]): string {
  const first = actions[0]
  switch (kind) {
    case 'read': {
      const byQuery = countBy(actions, (a) => String(a.query ?? '?'))
      const found = actions.reduce((sum, a) => sum + Number(a.result_count ?? 0), 0)
      return `${byQuery}, ${found} nodes/edges seen`
    }
    case 'walk': {
      const hops = actions.reduce((sum, a) => sum + (a.hops?.length ?? 0), 0)
      return `${hops} hop${hops === 1 ? '' : 's'} along ${
        actions.map((a) => (a.rel_path ?? []).join(' → ')).filter(Boolean).join('; ') || 'relations'
      }`
    }
    case 'write':
      return countBy(actions, (a) => String(a.node_type ?? '?'))
    case 'link': {
      // The relation and how it was established is the whole point of an edge.
      const rel = countBy(actions, (a) => String(a.edge_type || a.relation_id || 'rooted-in'))
      const mech = countBy(actions, (a) => String(a.established_by || 'structural'))
      return `${rel} · by ${mech}`
    }
    case 'model':
      return [
        first.duration_ms ? `${Math.round(Number(first.duration_ms) / 1000)}s` : '',
        first.completion_tokens ? `${first.completion_tokens} tokens out` : '',
      ].filter(Boolean).join(' · ')
    case 'step':
      return truncate(String(first.output_summary ?? ''), 140)
    case 'verify': {
      const count = Number(first.violation_count ?? 0)
      return count === 0 ? 'No violations' : `${count} violation${count === 1 ? '' : 's'}`
    }
    case 'repair':
      return `Rewrote ${(first.repaired_fields as string[] | undefined)?.join(', ') || 'the section'}`
    case 'validate': {
      const errors = Number(first.error_count ?? 0)
      return errors === 0 ? 'Schema valid' : `${errors} problem${errors === 1 ? '' : 's'}`
    }
    case 'error':
      return first.kind === 'regen'
        ? `Empty: ${(first.empty_fields as string[] | undefined)?.join(', ')}`
        : truncate(String(first.error ?? ''), 160)
    case 'retrieval':
      if (first.kind === 'retrieval_query') {
        return countBy(actions, (a) => `${a.retrieval_agent}: ${a.status}`)
      }
      return [
        first.strategy && `${first.strategy} strategy`,
        first.snippet_count ? `${first.snippet_count} snippets` : '',
        (first.retrieval_agents as string[] | undefined)?.join(', '),
      ].filter(Boolean).join(' · ')
    default:
      // An action kind this build has never heard of. Rather than an empty row,
      // show whatever it carries — the harness gains new kinds (retrieval
      // adapters next) faster than this file will be updated for them.
      return summariseUnknown(first)
  }
}

/** Best-effort one-liner for an action kind with no bespoke formatter. */
function summariseUnknown(action: DeepAction): string {
  const skip = new Set(['seq', 'kind', 'actor', 'phase', 'elapsed_ms', 'timestamp'])
  return Object.entries(action)
    .filter(([key, value]) => !skip.has(key) && value !== '' && value != null)
    .slice(0, 4)
    .map(([key, value]) => `${key}=${typeof value === 'object' ? JSON.stringify(value).slice(0, 40) : value}`)
    .join(' · ')
}

function toneFor(kind: WorkKind, action: DeepAction): DeepRow['tone'] {
  if (kind === 'error') return 'bad'
  if (kind === 'repair') return 'good'
  if (kind === 'link') return 'good'
  if (kind === 'verify') return Number(action.violation_count ?? 0) === 0 ? 'good' : 'warn'
  if (kind === 'validate') return Number(action.error_count ?? 0) === 0 ? 'good' : 'bad'
  return undefined
}

function countBy(actions: DeepAction[], key: (a: DeepAction) => string): string {
  const counts = new Map<string, number>()
  for (const action of actions) {
    const k = key(action)
    counts.set(k, (counts.get(k) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([k, n]) => (n === 1 ? k : `${n}× ${k}`))
    .join(', ')
}

function truncate(text: string, limit: number): string {
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trimEnd()}…`
}

/** Readable name for a phase, reused from the v1 timeline's vocabulary. */
export { phaseLabel } from './mergeTimeline'
