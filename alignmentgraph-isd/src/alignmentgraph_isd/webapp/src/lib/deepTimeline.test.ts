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
    context: { phase: 'assessment_designer', ...context },
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
    expect(rows[0].detail).toBe('plan_coverage(5)')
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
      action('phase_started', 'WorkflowOrchestrator', {}),
      action('node_read', 'ContentDesignerAgent', { query: 'get_node', result_count: 1 }),
      action('node_read', 'RubricDesignerAgent', { query: 'get_node', result_count: 1 }),
      action('phase_finished', 'WorkflowOrchestrator', {}),
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
      action('audit', 'WorkflowOrchestrator', {
        residual_gap_count: 0, gapped_relations: [], ready_to_aggregate: true,
      }),
    ])
    expect(rows).toHaveLength(1)  // audit in ONE_PER_ROW: never folded together
    expect(rows[0].title).toBe('Audit graph')
    expect(rows[0].detail).toBe('No relation gaps')
    expect(rows[0].tone).toBe('good')
  })

  it('flags a gapped residual audit as a warning', () => {
    const row = foldChronological([action('audit', 'WorkflowOrchestrator', {
      residual_gap_count: 2, gapped_relations: ['C4', 'P6'], ready_to_aggregate: false,
    })])[0]
    expect(row.detail).toBe('2 gaps (C4, P6)')
    expect(row.tone).toBe('warn')
  })
})
