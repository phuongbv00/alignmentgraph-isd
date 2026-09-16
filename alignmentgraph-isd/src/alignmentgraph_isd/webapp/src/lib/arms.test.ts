import { describe, expect, it } from 'vitest'
import { ARMS, DEFAULT_ARM, armOf } from './arms'

describe('ARMS', () => {
  it('covers the 2x2 exactly once', () => {
    // The table is written by hand, so the failure it guards against is a typo
    // that quietly duplicates one cell and drops another — leaving a run that
    // cannot be named by `armOf`.
    const cells = ARMS.map((arm) => `${arm.agentMode}x${arm.contextMode}`)
    expect(new Set(cells).size).toBe(4)
    expect(new Set(ARMS.map((arm) => arm.label)).size).toBe(4)
  })

  it('has exactly one default, which is what the run button starts', () => {
    expect(ARMS.filter((arm) => arm.isDefault)).toHaveLength(1)
    expect([DEFAULT_ARM.agentMode, DEFAULT_ARM.contextMode]).toEqual(['multi', 'graph'])
  })
})

describe('armOf', () => {
  it('names a run by the axes it reports', () => {
    expect(armOf('single', 'prose')?.label).toContain('Single-agent')
    expect(armOf('multi', 'graph')).toBe(DEFAULT_ARM)
  })

  it('names nothing when the run does not say', () => {
    // A run recorded before the axes rode in `stats` carries neither field, and
    // that is NOT the same as having run under the default — so it gets no
    // badge rather than an assumed one.
    expect(armOf(undefined, undefined)).toBeNull()
    expect(armOf('single', undefined)).toBeNull()
    expect(armOf('duo', 'prose')).toBeNull()
  })
})
