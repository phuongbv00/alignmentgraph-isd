import { describe, expect, it } from 'vitest'
import { parseServerTime, runStamp } from './time'

describe('parseServerTime', () => {
  it('reads a bare database timestamp as UTC, not as local time', () => {
    expect(parseServerTime('2026-09-08T02:10:59.496163').toISOString())
      .toBe('2026-09-08T02:10:59.496Z')
  })

  it('leaves an offset the server did send alone', () => {
    expect(parseServerTime('2026-09-07T17:30:10.105674+00:00').toISOString())
      .toBe('2026-09-07T17:30:10.105Z')
    expect(parseServerTime('2026-09-07T17:30:10Z').toISOString())
      .toBe('2026-09-07T17:30:10.000Z')
  })
})

describe('runStamp', () => {
  it('says so rather than rendering an Invalid Date', () => {
    expect(runStamp(undefined)).toBe('no timestamp')
    expect(runStamp('not a date')).toBe('no timestamp')
  })

  it('formats a real timestamp', () => {
    expect(runStamp('2026-09-08T02:10:59.496163')).not.toBe('no timestamp')
  })
})
