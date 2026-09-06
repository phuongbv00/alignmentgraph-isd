import { describe, expect, it } from 'vitest'
import { openReasonLabel, violationLabel } from './violations'

describe('violationLabel', () => {
  it('names every check the graph can mark a node with', () => {
    // The graph draws an amber border from `node_violations`, and the node
    // detail lists the same types by name. A type the border can carry but the
    // table cannot name would show a reader "something is wrong here" and then
    // hand them back the snake_case they came to the app to avoid.
    const marked = [
      'C1', 'C2', 'C3', 'C4', 'C5',
      'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9', 'P10', 'P11',
      'bloom', 'bloom_mismatch_assessment', 'bloom_mismatch_activity',
      'measurability', 'plan_coverage', 'item_completeness', 'evaluation_quality',
      'activity_engagement', 'rubric_consistency', 'evidence_alignment',
      'orphan_content', 'feasibility', 'actionability',
    ]
    for (const type of marked) {
      expect(violationLabel(type), type).not.toBe(type)
    }
  })

  it('names what the check ASSERTS, so a clean design reads as properties that hold', () => {
    expect(violationLabel('C2')).toBe('objective assessed by an assessment item')
    expect(violationLabel('item_completeness')).toBe('item can be administered as written')
  })

  it('falls back to the raw type rather than hiding an unknown one', () => {
    expect(violationLabel('some_future_check')).toBe('some_future_check')
  })
})

describe('openReasonLabel', () => {
  it('keeps a harness limit and a model limit apart', () => {
    // The distinction the ledger exists for: "we did not give it another turn"
    // is a parameter we chose, "it could not be fixed" is a result.
    expect(openReasonLabel('budget')).not.toBe(openReasonLabel('converged'))
    expect(openReasonLabel('budget')).toContain('budget')
  })
})
