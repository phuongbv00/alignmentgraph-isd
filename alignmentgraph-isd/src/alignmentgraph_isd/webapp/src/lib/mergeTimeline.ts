import type { RunEvent } from '../api/types'

/**
 * Folding the raw event stream into something readable.
 *
 * A run emits ~55 `node_edit` events in a handful of bursts. Listed one per row
 * they bury the eight steps that actually describe what happened, so
 * consecutive edits collapse into a single expandable row. Ordering is by the
 * server's `seq` throughout — never by timestamp, which is written in bursts
 * and is not reliably monotonic across the underlying streams.
 */

export interface TimelineRow {
  id: string
  seq: number
  kind: 'phase' | 'step' | 'edits' | 'verifier' | 'repair' | 'validation' | 'llm' | 'run' | 'other'
  title: string
  detail: string
  ts: string
  /** Grouped node edits, so the row can expand. */
  events: RunEvent[]
  tone?: 'good' | 'warn' | 'bad'
}

export function mergeTimeline(events: RunEvent[]): TimelineRow[] {
  const rows: TimelineRow[] = []
  const ordered = [...events].sort((a, b) => a.seq - b.seq)

  for (const event of ordered) {
    const previous = rows[rows.length - 1]

    switch (event.kind) {
      case 'node_edit': {
        // Fold into the previous run of edits rather than starting a new row.
        if (previous?.kind === 'edits') {
          previous.events.push(event)
          previous.title = `Wrote ${previous.events.length} graph node${previous.events.length === 1 ? '' : 's'}`
          previous.detail = summariseEdits(previous.events)
          continue
        }
        rows.push({
          id: `edits-${event.seq}`,
          seq: event.seq,
          kind: 'edits',
          title: 'Wrote 1 graph node',
          detail: summariseEdits([event]),
          ts: event.ts,
          events: [event],
        })
        continue
      }

      case 'phase_started':
        rows.push({
          id: `phase-${event.seq}`,
          seq: event.seq,
          kind: 'phase',
          title: phaseLabel(String(event.payload.phase ?? '')),
          detail: `Step ${event.payload.index} of ${event.payload.total}`,
          ts: event.ts,
          events: [event],
        })
        continue

      case 'agent_step':
        rows.push({
          id: `step-${event.seq}`,
          seq: event.seq,
          kind: 'step',
          title: `${event.payload.agent_name} — ${humanise(String(event.payload.action ?? ''))}`,
          detail: truncate(String(event.payload.output_summary ?? ''), 160),
          ts: event.ts,
          events: [event],
          tone: String(event.payload.action ?? '').includes('warning') ? 'warn' : undefined,
        })
        continue

      case 'verifier_event': {
        const count = Number(event.payload.violation_count ?? 0)
        rows.push({
          id: `verifier-${event.seq}`,
          seq: event.seq,
          kind: 'verifier',
          title: `Verification round ${event.payload.round}`,
          detail: count === 0 ? 'No violations' : `${count} violation${count === 1 ? '' : 's'}: ${byType(event.payload.by_type)}`,
          ts: event.ts,
          events: [event],
          tone: count === 0 ? 'good' : 'warn',
        })
        continue
      }

      case 'repair_event':
        rows.push({
          id: `repair-${event.seq}`,
          seq: event.seq,
          kind: 'repair',
          title: `Repaired ${event.payload.violation_type} on ${event.payload.node_id}`,
          detail: `${event.payload.agent} rewrote ${(event.payload.repaired_fields as string[])?.join(', ') || 'the section'}`,
          ts: event.ts,
          events: [event],
          tone: 'good',
        })
        continue

      case 'validation_event': {
        const errors = Number(event.payload.error_count ?? 0)
        rows.push({
          id: `validation-${event.seq}`,
          seq: event.seq,
          kind: 'validation',
          title: `Validated ${event.payload.scope}`,
          detail: errors === 0 ? 'Schema valid' : `${errors} problem${errors === 1 ? '' : 's'}`,
          ts: event.ts,
          events: [event],
          tone: errors === 0 ? 'good' : 'bad',
        })
        continue
      }

      case 'run_started':
        rows.push({
          id: `run-${event.seq}`, seq: event.seq, kind: 'run',
          title: 'Run started', detail: '', ts: event.ts, events: [event],
        })
        continue

      // Worth a row of its own: it records when the stop was asked for, which
      // is not when it took effect.
      case 'run_cancelling':
        rows.push({
          id: `run-${event.seq}`,
          seq: event.seq,
          kind: 'run',
          title: 'Cancellation requested',
          detail: String(event.payload.note ?? ''),
          ts: event.ts,
          events: [event],
          tone: 'warn',
        })
        continue

      case 'run_finished':
      case 'run_failed':
      case 'run_cancelled':
        rows.push({
          id: `run-${event.seq}`,
          seq: event.seq,
          kind: 'run',
          title: {
            run_finished: 'Run finished',
            run_failed: 'Run failed',
            run_cancelled: 'Run cancelled',
          }[event.kind],
          detail: String(event.payload.error ?? ''),
          ts: event.ts,
          events: [event],
          tone: event.kind === 'run_finished' ? 'good' : 'bad',
        })
        continue

      // phase_finished / llm_* / llm_call drive the header and the elapsed
      // timer. They are progress signals, not part of the recorded trace, so
      // they are deliberately absent from the list: what the timeline shows is
      // exactly what the run recorded.
      default:
        continue
    }
  }

  return rows
}

const PHASE_LABELS: Record<string, string> = {
  needs_context: 'Analysis — needs and context',
  objective_design: 'Design — learning objectives',
  assessment_design: 'Development — assessment',
  activity_material: 'Development — activities and materials',
  implementation_plan: 'Implementation — delivery plan',
  evaluation_revision: 'Evaluation — formative and summative',
  aggregate: 'Assembling the ADDIE output',
}

export function phaseLabel(phase: string): string {
  if (PHASE_LABELS[phase]) return PHASE_LABELS[phase]
  if (phase.endsWith('_qc')) {
    const base = phase.slice(0, -3)
    return `Checking ${(PHASE_LABELS[base] ?? humanise(base)).toLowerCase()}`
  }
  return humanise(phase)
}

function summariseEdits(events: RunEvent[]): string {
  const counts = new Map<string, number>()
  for (const event of events) {
    const type = String(event.payload.node_type ?? 'node')
    counts.set(type, (counts.get(type) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => `${count}× ${type}`)
    .join(', ')
}

function byType(value: unknown): string {
  if (!value || typeof value !== 'object') return ''
  return Object.entries(value as Record<string, number>)
    .map(([type, count]) => `${type}(${count})`)
    .join(', ')
}

function humanise(text: string): string {
  const spaced = text.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

function truncate(text: string, limit: number): string {
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trimEnd()}…`
}

