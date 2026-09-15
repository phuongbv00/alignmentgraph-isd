import { describe, expect, it } from 'vitest'
import { openReasonLabel, violationLabel } from './violations'

describe('violationLabel', () => {
  it('names every within-artifact check the graph can mark a node with', () => {
    // The graph draws an amber border from `node_violations`, and the node
    // detail lists the same types by name. A type the border can carry but the
    // table cannot name would show a reader "something is wrong here" and then
    // hand them back the snake_case they came to the app to avoid.
    const marked = [
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
    expect(violationLabel('item_completeness')).toBe('item can be administered as written')
  })

  it("takes a relation's wording from the payload, never from a table here", () => {
    // The 16 relations used to be hardcoded above, under a comment claiming
    // they came from `alignment.REGISTRY`. None of them did — every one was a
    // paraphrase and most reversed the direction ("activity scheduled by a
    // session guide" for `delivers`). The registry travels in the payload.
    const relations = {
      C2: { label: 'learning outcome assessed by assessment task' },
      P10: { label: 'session guide delivers activity' },
    }
    expect(violationLabel('C2', relations)).toBe('learning outcome assessed by assessment task')
    expect(violationLabel('P10', relations)).toBe('session guide delivers activity')
    // With no payload to hand, the bare id — not a word this system does not use.
    expect(violationLabel('C2')).toBe('C2')
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

  it('says an unsettled finding is unsettled rather than showing nothing', () => {
    // The ledger streams as it fills, so a row can be read before anything has
    // explained it. `Memory.settle` stamps `unexplained` on whatever is still
    // open at the end, so a BLANK reason means exactly "not settled yet" — and
    // stays that way forever on a cancelled run. Falling through to the raw
    // value printed an empty cell in the one column this tab exists for.
    const blank = openReasonLabel('')
    expect(blank).not.toBe('')
    for (const settled of ['converged', 'budget', 'unowned', 'unexplained']) {
      expect(blank).not.toBe(openReasonLabel(settled))
    }
  })
})
