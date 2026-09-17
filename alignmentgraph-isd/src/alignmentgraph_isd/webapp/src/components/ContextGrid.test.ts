import { describe, expect, it } from 'vitest'
import { thinkingOf } from './ContextGrid'
import type { ContextMessage } from '../api/types'

const turn = (extra: Partial<ContextMessage> = {}): ContextMessage => ({
  role: 'assistant',
  content: '',
  ...extra,
})

describe('thinkingOf', () => {
  it('is empty for a turn that carried no reasoning channel', () => {
    // The common case by far: a turn with no reasoning must render no fold at
    // all, and an empty collapsible is worse than none.
    expect(thinkingOf(turn())).toBe('')
    expect(thinkingOf(turn({ content: 'an ordinary reply' }))).toBe('')
  })

  it('treats a whitespace-only channel as no reasoning', () => {
    // A backend that reports the field on every reply, empty or not, would
    // otherwise put a fold on every turn in the transcript.
    expect(thinkingOf(turn({ reasoning: '   \n  ' }))).toBe('')
  })

  it('keeps the reasoning, trimmed', () => {
    expect(thinkingOf(turn({ reasoning: '\n  Three gaps, so three objectives. \n' })))
      .toBe('Three gaps, so three objectives.')
  })
})
