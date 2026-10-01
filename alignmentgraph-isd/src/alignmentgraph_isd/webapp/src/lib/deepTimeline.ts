import type { DeepAction } from '../api/types'
import { violationLabel } from './violations'

/**
 * Turning the deep trajectory into something a person can read — in TIME order.
 *
 * A run logs well over a thousand actions, most of them graph reads. The fold
 * strictly follows the recorded order: only an unbroken run of the same kind
 * of work collapses into one row, which stays at its chronological position.
 * Different kinds are never merged across time, so a self-check loop reads as
 * it happened — check (5 violations) → repair → check (0) — instead of the
 * repairs being filed under a separate per-kind pile (the earlier grid did
 * exactly that, and it read as "5 violations became 0 with nothing between").
 */

export type WorkKind =
  | 'read'      // looked at the graph
  | 'walk'      // followed relations
  | 'write'     // wrote nodes
  | 'link'      // drew a NEW alignment edge (op=add: real establishment)
  | 'relink'    // re-verified existing edges (op=refresh: the deterministic
                // establishers re-derived them — self-validation
                // machinery confirming the alignment still holds, not design)
  | 'model'     // called the model
  | 'step'      // recorded a step of its own
  | 'check'
  | 'repair'
  | 'validate'
  | 'audit'     // the residual whole-graph audit, at aggregation
  | 'plan'      // split a stage's work into sets and dispatched them (fan-out)
  | 'route'     // handed a residual cross-artifact violation to its owner
  | 'retrieval'
  | 'compact'  // folded old turns away to stay inside the window
  | 'error'
  | 'phase'
  | 'other'

export interface DeepRow {
  id: string
  action: string
  kind: WorkKind
  title: string
  detail: string
  actions: DeepAction[]
  /** Collapsed runs show how many were folded together. */
  count: number
  tone?: 'good' | 'warn' | 'bad'
}

const KIND_OF: Record<string, WorkKind> = {
  node_read: 'read',
  edge_read: 'read',
  edge_walk: 'walk',
  node_write: 'write',
  doc_write: 'write',
  edge_write: 'link',
  dev_plan: 'plan',
  reconcile: 'route',
  llm_call: 'model',
  agent_step: 'step',
  check: 'check',
  repair: 'repair',
  validate: 'validate',
  audit: 'audit',
  retrieval: 'retrieval',
  retrieval_query: 'retrieval',
  agent_error: 'error',
  llm_error: 'error',
  salvage_truncated: 'error',
  invalid_action: 'error',
  submit_rejected: 'error',
  submit_invalid_final: 'error',
  repeated_tool_call: 'error',
  commit_invalid_section: 'error',
  agentic_gave_up: 'error',
  budget_exhausted: 'error',
  run_stopped: 'error',
  excess_artifacts_trimmed: 'error',
  tool_binding_unavailable: 'error',
  tool_call_markup_recovered: 'error',
  duplicate_submit: 'error',
  bare_artifact_wrapped: 'error',
  dropped_argument: 'error',
  argument_reshaped: 'error',
  tool_choice_downgraded: 'error',
  read_of_assignment_id: 'error',
  repair_declined: 'error',
  calls_not_executed: 'error',
  repair_window_closed: 'error',
  stage_abandoned: 'error',
  // Not an error: the loop managing its own window. Its RATE is a measurement
  // (the `agent_mode` axis's price), so it gets a beat of its own rather than
  // a red one.
  context_compacted: 'compact',
  // Not an error either: the model produced the same element twice and the
  // harness recorded that rather than absorbing it. How much padding a size
  // does is a finding, so it gets a beat.
  duplicate_element_dropped: 'compact',
  // Retired 2026-09-01 with the scripted rescue; kept so an archived run still
  // renders as what it recorded rather than as an unknown action.
  agentic_fallback: 'error',
  retry: 'error',
  regen_empty_section: 'error',
  phase_started: 'phase',
  phase_finished: 'phase',
}

export function workKind(action: DeepAction): WorkKind {
  // Same taxonomy action, two different kinds of work: an `edge_write` with
  // op=add establishes a new alignment edge; op=refresh only re-derives an
  // existing one (idempotent re-verification at self-validation).
  // Telling them apart is what keeps "the orchestrator drew 146 edges" from
  // ever appearing — the orchestrator only re-verifies.
  if (action.action === 'edge_write' && action.context.op === 'refresh') return 'relink'
  return KIND_OF[action.action] ?? 'other'
}

/** Never folded into a run, even when consecutive: each of these is one
 *  distinct beat of the story (its own round, its own fix, its own step). */
const ONE_PER_ROW = new Set<WorkKind>(
  ['check', 'repair', 'validate', 'audit', 'plan', 'route', 'step', 'model', 'error'],
)

/** `relations` carries each C/P relation's canonical wording, straight from the
 *  graph payload's `relation_coverage` (which is `alignment.REGISTRY`). Passed
 *  down rather than kept in a table here: a relation is named in one place. */
export function foldChronological(
  actions: DeepAction[],
  relations?: Record<string, { label?: string }>,
): DeepRow[] {
  const rows: DeepRow[] = []

  for (const action of actions) {
    // Phase markers define the boundaries; they are not work in themselves.
    if (action.action === 'phase_started' || action.action === 'phase_finished') continue

    const kind = workKind(action)
    const previous = rows[rows.length - 1]
    // Only an UNBROKEN run of the same kind of bulk work collapses; the row
    // stays at its chronological position, so nothing is reordered.
    if (
      previous &&
      previous.kind === kind &&
      previous.action === action.action &&
      previous.actions[previous.actions.length - 1].agent === action.agent &&
      !ONE_PER_ROW.has(kind)
    ) {
      previous.actions.push(action)
      previous.count = previous.actions.length
      previous.title = titleFor(kind, previous.actions)
      previous.detail = detailFor(kind, previous.actions, relations)
      continue
    }

    rows.push({
      id: `row-${rows.length}-${action.action}-${kind}`,
      action: action.action,
      kind,
      title: titleFor(kind, [action]),
      detail: detailFor(kind, [action], relations),
      actions: [action],
      count: 1,
      tone: toneFor(kind, action),
    })
  }

  return rows
}

// Titles name the action, present tense (verb first — "Generate", not "Called
// the model"): this is a label for a kind of work, not a narration of history.
function titleFor(kind: WorkKind, actions: DeepAction[]): string {
  const first = actions[0]
  const context = first.context
  const n = actions.length
  switch (kind) {
    case 'read':
      return n === 1 ? 'Read graph' : `Read graph ${n}×`
    case 'walk':
      return n === 1 ? 'Follow relations' : `Follow relations ${n}×`
    case 'write':
      return n === 1 ? `Write ${context.node_id}` : `Write ${n} nodes`
    case 'link':
      return n === 1
        ? `Link ${context.source} → ${context.target}`
        : `Draw ${n} alignment edges`
    case 'relink':
      return n === 1
        ? `Re-verify ${context.source} → ${context.target}`
        : `Re-verify ${n} alignment edges`
    case 'model':
      return 'Generate'
    case 'step':
      return String(context.agent_action ?? 'Step')
    case 'check': {
      // Count-first, not round-first: the stored round number is a run-global
      // counter, so "round 4" as the first check of a phase only confuses.
      const violations = Number(context.violation_count ?? 0)
      return violations === 0
        ? 'Self-check — clean'
        : `Self-check — ${violations} violation${violations === 1 ? '' : 's'}`
    }
    case 'repair':
      return context.violation_type
        ? `Repair ${context.violation_type} on ${context.node_id ?? 'design'}`
        : 'Apply design revision'
    case 'validate':
      return `Validate ${context.scope ?? 'output'}`
    case 'audit':
      return 'Audit graph'
    case 'plan': {
      const sets = Number(context.set_count ?? 0)
      return `Split ${context.family ?? 'work'} into ${sets} work set${sets === 1 ? '' : 's'}`
    }
    case 'route': {
      const routed = Number(context.routed ?? 0)
      return `Route ${routed} residual violation${routed === 1 ? '' : 's'} to ${context.family ?? 'owner'}`
    }
    case 'retrieval':
      if (first.action === 'retrieval_query') {
        return n === 1
          ? `Query ${context.retrieval_agent}`
          : `Query ${n} sources`
      }
      return `Retrieval: ${context.decision}`
    case 'compact':
      return first.context.dropped
        ? `Compact context (${first.context.dropped} turns folded)`
        : 'Compact context'
    case 'error':
      return RECOVERY_LABEL[first.action] ?? first.action
    default:
      return first.action
  }
}

function detailFor(kind: WorkKind, actions: DeepAction[], relations?: Record<string, { label?: string }>): string {
  const first = actions[0]
  const context = first.context
  switch (kind) {
    case 'read': {
      const byQuery = countBy(actions, (a) => String(a.context.query ?? '?'))
      const found = actions.reduce((sum, a) => sum + Number(a.context.result_count ?? 0), 0)
      return `${byQuery}, ${found} nodes/edges seen`
    }
    case 'walk': {
      const hops = actions.reduce((sum, a) => sum + (a.context.hops?.length ?? 0), 0)
      return `${hops} hop${hops === 1 ? '' : 's'} along ${
        actions.map((a) => (a.context.rel_path ?? []).join(' → ')).filter(Boolean).join('; ') || 'relations'
      }`
    }
    case 'write':
      // A graph write names its node type; a prose write names the blackboard
      // document key. Both answer "what did this produce".
      return countBy(actions, (a) => String(a.context.node_type ?? a.context.key ?? '?'))
    case 'link':
    case 'relink': {
      // The relation and how it was established is the whole point of an edge.
      const rel = countBy(actions, (a) => String(a.context.edge_type || a.context.relation_id || 'rooted-in'))
      const mech = countBy(actions, (a) => String(a.context.established_by || 'structural'))
      return `${rel} · by ${mech}`
    }
    case 'model':
      return [
        context.duration_ms ? `${Math.round(Number(context.duration_ms) / 1000)}s` : '',
        context.completion_tokens ? `${context.completion_tokens} tokens out` : '',
      ].filter(Boolean).join(' · ')
    case 'step':
      return truncate(String(context.output_summary ?? ''), 140)
    case 'check': {
      const byType = context.by_type as Record<string, number> | undefined
      if (byType && Object.keys(byType).length > 0) {
        // Named, not raw. `bloom_mismatch_activity(2)` told a reader the check
        // fired and nothing else — and it was the app's only word for it.
        return Object.entries(byType)
          .map(([type, n]) => `${violationLabel(type, relations)}${n > 1 ? ` ×${n}` : ''}`)
          .join(', ')
      }
      return 'No violations'
    }
    case 'repair':
      // The repair record now carries the rule's own narrative — the most
      // informative one-liner it has.
      if (context.output_summary) return truncate(String(context.output_summary), 140)
      return (context.repaired_fields as string[] | undefined)?.length
        ? `Rewrote ${(context.repaired_fields as string[]).join(', ')}`
        : String(context.rule ?? 'Applied deterministic repair')
    case 'validate': {
      const errors = Number(context.error_count ?? 0)
      return errors === 0 ? 'Schema valid' : `${errors} problem${errors === 1 ? '' : 's'}`
    }
    case 'plan': {
      // `source` is the one thing that says whether the agent chose this split
      // or a deterministic fallback did — the difference between a dispatch it
      // reasoned about and one it was handed.
      const ids = ((context.sets as { set_id?: string }[] | undefined) ?? [])
        .map((set) => String(set.set_id ?? '')).filter(Boolean)
      return [
        `grouping from ${context.source ?? '?'}`,
        ids.length ? ids.slice(0, 4).join(', ') + (ids.length > 4 ? ` +${ids.length - 4}` : '') : '',
        Number(context.dropped_refs ?? 0) ? `${context.dropped_refs} dangling refs dropped` : '',
        Number(context.appended_sets ?? 0) ? `${context.appended_sets} sets appended for coverage` : '',
      ].filter(Boolean).join(' · ')
    }
    case 'route':
      return (context.violation_types as string[] | undefined)?.map((type) => violationLabel(type, relations)).join(', ') || 'no violation types recorded'
    case 'audit': {
      const gaps = Number(context.residual_gap_count ?? 0)
      const gapped = (context.gapped_relations as string[] | undefined) ?? []
      return gaps === 0
        ? 'No relation gaps'
        : `${gaps} gap${gaps === 1 ? '' : 's'} (${gapped.join(', ')})`
    }
    case 'error':
      return truncate(
        String(context.output_summary ?? context.error ?? context.input_summary ?? ''), 160,
      )
    case 'retrieval':
      if (first.action === 'retrieval_query') {
        return countBy(actions, (a) => `${a.context.retrieval_agent}: ${a.context.status}`)
      }
      return [
        context.strategy && `${context.strategy} strategy`,
        context.snippet_count ? `${context.snippet_count} snippets` : '',
        (context.retrieval_agents as string[] | undefined)?.join(', '),
      ].filter(Boolean).join(' · ')
    default:
      // An action kind this build has never heard of. Rather than an empty row,
      // show whatever it carries — the harness gains new kinds (retrieval
      // adapters next) faster than this file will be updated for them.
      return summariseUnknown(first)
  }
}

const RECOVERY_LABEL: Record<string, string> = {
  retry: 'Retry model call',
  regen_empty_section: 'Regenerate empty section',
  agent_error: 'Agent error',
  llm_error: 'Model error',
  salvage_truncated: 'Salvage truncated response',
  invalid_action: 'Reject invalid action',
  submit_rejected: 'Reject invalid submission',
  submit_invalid_final: 'Reject final submission',
  repeated_tool_call: 'Skip repeated tool call',
  commit_invalid_section: 'Skip invalid section',
  agentic_gave_up: 'Give up on this step',
  budget_exhausted: 'Run out of turns',
  run_stopped: 'Stop the run: no course modules',
  excess_artifacts_trimmed: 'Trim a work set to its stated count',
  tool_binding_unavailable: 'Backend accepted no tool binding',
  tool_call_markup_recovered: 'Recover tool call left as text',
  duplicate_submit: 'Skip duplicate submission',
  bare_artifact_wrapped: 'Wrap bare artifact',
  dropped_argument: 'Drop unreadable argument',
  argument_reshaped: 'Re-container string as list',
  tool_choice_downgraded: 'Backend refused forced tool call',
  read_of_assignment_id: 'Point read back to the assignment',
  repair_declined: 'Close stage with issues the agent declined',
  agentic_fallback: 'Use fallback',
}

/** Best-effort one-liner for an action kind with no bespoke formatter. */
function summariseUnknown(action: DeepAction): string {
  return Object.entries(action.context)
    .filter(([, value]) => value !== '' && value != null)
    .slice(0, 4)
    .map(([key, value]) => `${key}=${typeof value === 'object' ? JSON.stringify(value).slice(0, 40) : value}`)
    .join(' · ')
}

function toneFor(kind: WorkKind, action: DeepAction): DeepRow['tone'] {
  if (kind === 'error') return 'bad'
  if (kind === 'repair') return 'good'
  if (kind === 'link') return 'good'
  if (kind === 'check') return Number(action.context.violation_count ?? 0) === 0 ? 'good' : 'warn'
  if (kind === 'validate') return Number(action.context.error_count ?? 0) === 0 ? 'good' : 'bad'
  if (kind === 'audit') return Number(action.context.residual_gap_count ?? 0) === 0 ? 'good' : 'warn'
  // A grouping the agent proposed is the intended path; a fallback grouping is
  // the harness deciding for it, which is worth seeing at a glance.
  if (kind === 'plan') return action.context.source === 'llm' ? 'good' : 'warn'
  if (kind === 'route') return 'warn'
  if (kind === 'compact') return 'warn'
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

/** Readable name for a phase; the vocabulary lives with the phase timeline. */
export { phaseLabel } from './phaseTimeline'
