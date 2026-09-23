import { afterEach, describe, expect, it } from 'vitest'
import { ARMS } from './arms'
import {
  DEFAULT_RUN_SETTINGS, MAX_WORKERS, armKey, clampWorkers, describe as describeSettings,
  isDefault, loadRunSettings, saveRunSettings, toRunOptions,
} from './runSettings'

const store = new Map<string, string>()
globalThis.localStorage = {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => { store.set(key, value) },
  removeItem: (key: string) => { store.delete(key) },
  clear: () => store.clear(),
  key: () => null,
  get length() { return store.size },
} as Storage

afterEach(() => store.clear())

describe('toRunOptions', () => {
  it('sends no body for the default run', () => {
    expect(isDefault(DEFAULT_RUN_SETTINGS)).toBe(true)
    expect(toRunOptions(DEFAULT_RUN_SETTINGS)).toBeUndefined()
    expect(describeSettings(DEFAULT_RUN_SETTINGS)).toEqual([])
  })

  it('sends only what differs from the default', () => {
    const single = ARMS.find((arm) => arm.agentMode === 'single' && arm.contextMode === 'prose')!
    const settings = { armKey: armKey(single), fullDevelopment: true, fanoutWorkers: 3 }
    expect(isDefault(settings)).toBe(false)
    expect(toRunOptions(settings)).toEqual({
      agent_mode: 'single', context_mode: 'prose', development_mode: 'full', fanout_workers: 3,
    })
    expect(toRunOptions({ ...DEFAULT_RUN_SETTINGS, fanoutWorkers: 2 }))
      .toEqual({ fanout_workers: 2 })
  })
})

describe('clampWorkers', () => {
  it('keeps the count inside what the server accepts', () => {
    expect(clampWorkers(0)).toBe(1)
    expect(clampWorkers(99)).toBe(MAX_WORKERS)
    expect(clampWorkers('abc')).toBe(1)
    expect(clampWorkers(2.6)).toBe(3)
  })
})

describe('stored settings', () => {
  it('round-trip', () => {
    const settings = { ...DEFAULT_RUN_SETTINGS, fullDevelopment: true, fanoutWorkers: 4 }
    saveRunSettings(settings)
    expect(loadRunSettings()).toEqual(settings)
  })

  it('fall back to the default on anything unreadable', () => {
    store.set('agisd.runSettings', '{not json')
    expect(loadRunSettings()).toEqual(DEFAULT_RUN_SETTINGS)
    store.set('agisd.runSettings', JSON.stringify({ armKey: 'triple-agent', fanoutWorkers: 50 }))
    expect(loadRunSettings()).toEqual({ ...DEFAULT_RUN_SETTINGS, fanoutWorkers: MAX_WORKERS })
  })
})
