import { describe, expect, it } from 'vitest'
import { mergeTimeline, phaseLabel } from './mergeTimeline'
import type { RunEvent } from '../api/types'

let seq = 0
function event(kind: RunEvent['kind'], payload: Record<string, unknown> = {}): RunEvent {
  seq += 1
  return { seq, kind, ts: new Date(2026, 0, 1, 12, 0, seq).toISOString(), payload }
}

describe('mergeTimeline', () => {
  it('collapses a burst of node edits into one row', () => {
    // A real run writes ~55 of these in a handful of bursts; one row each
    // would bury the eight steps that describe what actually happened.
    seq = 0
    const events = [
      event('agent_step', { agent_name: 'NeedsContextAgent', action: 'needs_analysis', output_summary: 'ok' }),
      ...Array.from({ length: 12 }, () => event('node_edit', { node_type: 'gap', node_id: 'gap:GAP-01' })),
      event('agent_step', { agent_name: 'ObjectiveDesignAgent', action: 'design_objectives', output_summary: 'ok' }),
    ]

    const rows = mergeTimeline(events)
    expect(rows).toHaveLength(3)
    expect(rows[1].kind).toBe('edits')
    expect(rows[1].title).toBe('Wrote 12 graph nodes')
    expect(rows[1].detail).toBe('12× gap')
    expect(rows[1].events).toHaveLength(12)
  })

  it('summarises mixed node types in a burst', () => {
    seq = 0
    const rows = mergeTimeline([
      event('node_edit', { node_type: 'objective' }),
      event('node_edit', { node_type: 'objective' }),
      event('node_edit', { node_type: 'media' }),
    ])
    expect(rows[0].detail).toBe('2× objective, 1× media')
  })

  it('orders by the server sequence, not by arrival or timestamp', () => {
    // Timestamps on the underlying trace are written in bursts and are not
    // reliably monotonic across streams; seq is assigned from one thread.
    seq = 0
    const first = event('agent_step', { agent_name: 'A', action: 'x', output_summary: '' })
    const second = event('agent_step', { agent_name: 'B', action: 'y', output_summary: '' })
    second.ts = new Date(2020, 0, 1).toISOString() // earlier wall clock, later seq

    const rows = mergeTimeline([second, first])
    expect(rows.map((r) => r.seq)).toEqual([first.seq, second.seq])
  })

  it('keeps phase boundaries as headings', () => {
    seq = 0
    const rows = mergeTimeline([
      event('phase_started', { phase: 'objective_design', index: 3, total: 13 }),
      event('agent_step', { agent_name: 'ObjectiveDesignAgent', action: 'design_objectives', output_summary: '' }),
    ])
    expect(rows[0].kind).toBe('phase')
    expect(rows[0].title).toBe('Design — learning objectives')
    expect(rows[0].detail).toBe('Step 3 of 13')
  })

  it('drops the events that drive the header rather than the list', () => {
    seq = 0
    const rows = mergeTimeline([
      event('llm_call', { llm_calls: 1 }),
      event('phase_finished', { phase: 'x' }),
    ])
    expect(rows).toHaveLength(0)
  })

  it('tones verification and validation by outcome', () => {
    seq = 0
    const rows = mergeTimeline([
      event('verifier_event', { round: 1, violation_count: 0, by_type: {} }),
      event('verifier_event', { round: 2, violation_count: 2, by_type: { R3: 2 } }),
      event('validation_event', { scope: 'addie_output', error_count: 0 }),
      event('validation_event', { scope: 'addie_output', error_count: 3 }),
    ])
    expect(rows.map((r) => r.tone)).toEqual(['good', 'warn', 'good', 'bad'])
    expect(rows[1].detail).toContain('R3(2)')
  })

  it('describes a repair by what it rewrote', () => {
    seq = 0
    const rows = mergeTimeline([
      event('repair_event', {
        agent: 'ActivityMaterialAgent',
        violation_type: 'R8',
        node_id: 'activity_0',
        repaired_fields: ['learning_activities'],
      }),
    ])
    expect(rows[0].title).toBe('Repaired R8 on activity_0')
    expect(rows[0].detail).toContain('learning_activities')
    expect(rows[0].tone).toBe('good')
  })

  it('records when a stop was asked for, separately from when it took effect', () => {
    seq = 0
    const rows = mergeTimeline([
      event('run_cancelling', { note: 'Stopping after the current model call finishes.' }),
      event('run_cancelled', {}),
    ])
    expect(rows.map((r) => r.title)).toEqual(['Cancellation requested', 'Run cancelled'])
    expect(rows[0].tone).toBe('warn')
    expect(rows[0].detail).toContain('current model call')
  })

  it('marks how a run ended', () => {
    seq = 0
    expect(mergeTimeline([event('run_finished', {})])[0].tone).toBe('good')
    seq = 0
    expect(mergeTimeline([event('run_failed', { error: 'boom' })])[0].detail).toBe('boom')
    seq = 0
    expect(mergeTimeline([event('run_cancelled', {})])[0].title).toBe('Run cancelled')
  })
})

describe('phaseLabel', () => {
  it('names the ADDIE phases in the designer\'s terms', () => {
    expect(phaseLabel('needs_context')).toBe('Analysis — needs and context')
    expect(phaseLabel('evaluation_revision')).toBe('Evaluation — formative and summative')
  })

  it('describes a QC node as checking the phase it follows', () => {
    expect(phaseLabel('assessment_design_qc')).toBe('Checking development — assessment')
  })

  it('falls back to a readable form for anything unrecognised', () => {
    expect(phaseLabel('some_new_phase')).toBe('Some new phase')
  })
})
