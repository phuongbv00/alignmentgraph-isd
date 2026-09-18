import { describe, expect, it } from 'vitest'
import { foldChronological, workKind } from './deepTimeline'
import type { DeepAction } from '../api/types'

let tick = 0
function action(name: string, agent: string, context: Record<string, unknown> = {}): DeepAction {
  tick += 1
  return {
    timestamp: new Date(2026, 0, 1, 12, 0, 0, tick).toISOString(),
    agent,
    action: name,
    context: { phase: 'assessment', ...context },
  }
}

describe('foldChronological', () => {
  it('keeps the self-check loop in recorded order — check, repair, check', () => {
    tick = 0
    const rows = foldChronological([
      action('check', 'AssessmentDesignerAgent', { round: 4, violation_count: 5, by_type: { plan_coverage: 5 } }),
      action('node_read', 'AssessmentDesignerAgent', { query: 'get_node', result_count: 1 }),
      action('node_write', 'AssessmentDesignerAgent', { op: 'add', node_id: 'assessment:AT-F-01', node_type: 'assessment' }),
      action('repair', 'AssessmentDesignerAgent', {
        violation_type: 'plan_coverage', node_id: 'assessment',
        repaired_fields: ['assessment_tools'], rule: 'repair_plan_coverage',
        output_summary: 'Added AT-F-01 items promised by the plan.',
      }),
      action('check', 'AssessmentDesignerAgent', { round: 5, violation_count: 0, by_type: {} }),
    ])

    expect(rows.map((row) => row.kind)).toEqual(['check', 'read', 'write', 'repair', 'check'])
    expect(rows[0].title).toBe('Self-check — 5 violations')
    // Named, not raw: `plan_coverage(5)` told a reader the check fired and
    // nothing else, and it was the app's only word for that check.
    expect(rows[0].detail).toBe('every promised assessment pair is realised ×5')
    expect(rows[3].title).toBe('Repair plan_coverage on assessment')
    expect(rows[3].detail).toContain('Added AT-F-01')
    expect(rows[4].title).toBe('Self-check — clean')
  })

  it('collapses only an unbroken run of the same bulk work, in place', () => {
    tick = 0
    const rows = foldChronological([
      action('node_read', 'A', { query: 'get_node', result_count: 1 }),
      action('node_read', 'A', { query: 'get_node', result_count: 1 }),
      action('node_read', 'A', { query: 'element_nodes', result_count: 5 }),
      action('edge_write', 'A', { op: 'add', edge_type: 'C2-assessed_by', source: 'x', target: 'y' }),
      action('node_read', 'A', { query: 'get_node', result_count: 1 }),
    ])

    // The read run before the edge and the read after it stay SEPARATE rows:
    // folding across the edge_write would reorder the story.
    expect(rows.map((row) => [row.kind, row.count])).toEqual([
      ['read', 3], ['link', 1], ['read', 1],
    ])
    expect(rows[0].title).toBe('Read graph 3×')
  })

  it('never folds beats that are each their own story step, even when consecutive', () => {
    tick = 0
    const rows = foldChronological([
      action('check', 'A', { round: 1, violation_count: 2, by_type: { bloom: 2 } }),
      action('check', 'A', { round: 2, violation_count: 0, by_type: {} }),
      action('repair', 'A', { violation_type: 'bloom', node_id: 'objective', repaired_fields: ['x'] }),
      action('repair', 'A', { violation_type: 'C4', node_id: 'activity', repaired_fields: ['y'] }),
    ])
    expect(rows).toHaveLength(4)
  })

  it('does not fold across an agent change, and drops phase boundaries', () => {
    tick = 0
    const rows = foldChronological([
      action('phase_started', 'Orchestrator', {}),
      action('node_read', 'ContentDesignerAgent', { query: 'get_node', result_count: 1 }),
      action('node_read', 'MaterialDeveloperAgent', { query: 'get_node', result_count: 1 }),
      action('phase_finished', 'Orchestrator', {}),
    ])
    expect(rows).toHaveLength(2)
    expect(rows.every((row) => row.count === 1)).toBe(true)
  })

  it('splits edge refreshes from new edges by op', () => {
    const add = action('edge_write', 'A', { op: 'add' })
    const refresh = action('edge_write', 'A', { op: 'refresh' })
    expect(workKind(add)).toBe('link')
    expect(workKind(refresh)).toBe('relink')
    const rows = foldChronological([add, refresh])
    expect(rows.map((row) => row.kind)).toEqual(['link', 'relink'])
  })

  it('describes the residual audit as its own beat', () => {
    tick = 0
    const rows = foldChronological([
      action('audit', 'Orchestrator', {
        residual_gap_count: 0, gapped_relations: [], ready_to_aggregate: true,
      }),
    ])
    expect(rows).toHaveLength(1)  // audit in ONE_PER_ROW: never folded together
    expect(rows[0].title).toBe('Audit graph')
    expect(rows[0].detail).toBe('No relation gaps')
    expect(rows[0].tone).toBe('good')
  })

  it('describes a fan-out as the dispatch it was, and flags a fallback split', () => {
    tick = 0
    const [chosen] = foldChronological([
      action('dev_plan', 'Orchestrator', {
        family: 'activity_designer', set_count: 2, source: 'llm', dropped_refs: 0,
        appended_sets: 0, sets: [{ set_id: 'AS1' }, { set_id: 'AS2' }],
      }),
    ])
    expect(chosen.kind).toBe('plan')
    expect(chosen.title).toBe('Split activity_designer into 2 work sets')
    expect(chosen.detail).toContain('grouping from llm')
    expect(chosen.detail).toContain('AS1, AS2')
    // A grouping the agent proposed is the intended path; one the harness had
    // to derive for it is the fact a reader most needs off this row.
    expect(chosen.tone).toBe('good')

    const [derived] = foldChronological([
      action('dev_plan', 'Orchestrator', {
        family: 'activity_designer', set_count: 1, source: 'fallback',
        dropped_refs: 2, appended_sets: 1, sets: [{ set_id: 'AS1' }],
      }),
    ])
    expect(derived.tone).toBe('warn')
    expect(derived.detail).toContain('2 dangling refs dropped')
    expect(derived.detail).toContain('1 sets appended for coverage')
  })

  it('names the family a residual violation was routed to', () => {
    tick = 0
    const [row] = foldChronological([
      action('reconcile', 'AssessmentDesignerAgent', {
        family: 'assessment_designer', routed: 3,
        violation_types: ['item_completeness', 'plan_coverage'],
      }),
    ])
    // Routing is the decomposition axis expressed at repair time, so the row
    // has to say who it went to, not only that something was repaired.
    expect(row.kind).toBe('route')
    expect(row.title).toBe('Route 3 residual violations to assessment_designer')
    expect(row.detail).toBe(
      'item can be administered as written, every promised assessment pair is realised')
  })

  it('reads a prose write as an artifact, keyed by its document', () => {
    tick = 0
    const [row] = foldChronological([
      action('doc_write', 'OutcomeDesignerAgent', { key: 'objective', field_count: 4 }),
    ])
    expect(row.kind).toBe('write')
    expect(row.detail).toBe('objective')
  })

  it('labels the agentic loop\'s own failure modes', () => {
    tick = 0
    const rows = foldChronological([
      action('agentic_gave_up', 'ContentDesignerAgent', { output_summary: 'no valid submit' }),
      action('tool_call_markup_recovered', 'ContentDesignerAgent', { output_summary: 'text call' }),
    ])
    expect(rows.map((row) => row.kind)).toEqual(['error', 'error'])
    expect(rows[0].title).toBe('Give up on this step')
    // Not a model mistake: the serving stack left a well-formed call as text
    // and the loop recovered it. It is on this list so the RATE stays visible.
    expect(rows[1].title).toBe('Recover tool call left as text')
  })

  it('flags a gapped residual audit as a warning', () => {
    const row = foldChronological([action('audit', 'Orchestrator', {
      residual_gap_count: 2, gapped_relations: ['C4', 'P6'], ready_to_aggregate: false,
    })])[0]
    expect(row.detail).toBe('2 gaps (C4, P6)')
    expect(row.tone).toBe('warn')
  })
})
