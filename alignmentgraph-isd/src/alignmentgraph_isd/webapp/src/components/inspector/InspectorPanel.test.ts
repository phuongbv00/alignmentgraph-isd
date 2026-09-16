import { describe, expect, it } from 'vitest'
import { bloomFlag } from './InspectorPanel'
import type { ObjectiveAlignment } from '../../api/types'

/** An objective with no C2 and no C3 edge: the two Bloom checks group by the
 *  edges they read, so neither ran, and the payload says so with `null`. */
const unassessed: ObjectiveAlignment = {
  bloom_ok: true,
  bloom_assessment_ok: null,
  bloom_activity_ok: null,
  aligned: false,
  legs: [
    { relation_id: 'C2', verb: 'assessed_by', label: 'assessment task', ok: false },
    { relation_id: 'C3', verb: 'practiced_by', label: 'activity', ok: false },
    { relation_id: 'C4', verb: 'prepares_for', label: 'assessment task', ok: false },
  ],
}

describe('bloomFlag', () => {
  it('keeps "not checked" apart from "checked and fine"', () => {
    // The defect: `??` fell through a declared null to `bloom_ok`, so this
    // objective drew a green "assessed at its own Bloom level (C2)" beside
    // its own red C2 leg.
    expect(bloomFlag(unassessed, 'bloom_assessment_ok')).toBeNull()
    expect(bloomFlag(unassessed, 'bloom_activity_ok')).toBeNull()
    expect(unassessed.bloom_ok).toBe(true)
  })

  it('reports the rule as it landed when it did run', () => {
    const flags = { ...unassessed, bloom_assessment_ok: false, bloom_activity_ok: true }
    expect(bloomFlag(flags, 'bloom_assessment_ok')).toBe(false)
    expect(bloomFlag(flags, 'bloom_activity_ok')).toBe(true)
  })

  it('falls back to the union for an archived run that never split it', () => {
    // 29 of the 36 archived dumps carry `bloom_ok` alone. An ABSENT key is not
    // a null: that run gave an answer, just a coarser one.
    const archived: ObjectiveAlignment = { bloom_ok: false, aligned: false }
    expect(bloomFlag(archived, 'bloom_assessment_ok')).toBe(false)
    expect(bloomFlag(archived, 'bloom_activity_ok')).toBe(false)
  })
})
