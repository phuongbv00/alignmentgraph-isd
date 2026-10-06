import { useEffect, useState } from 'react'
import type { AgentMode, ContextMode } from '../api/types'
import { ARMS, DEFAULT_ARM, type Arm } from './arms'

/**
 * What the NEXT run is started under: the ablation arm, and how many of one
 * family's Developers run at once.
 *
 * Remembered in this browser, because it is a posture the reader sets once and
 * reruns under. What a run WAS is recorded on the run itself (the badges in the
 * run header read the server's resolved values), so remembering this cannot
 * make an earlier run ambiguous.
 */
export interface RunSettings {
  /** `${agentMode}-${contextMode}`, resolved through `ARMS`. */
  armKey: string
  /** 1 = the Developers run one after another. */
  fanoutWorkers: number
}

/** The server's own bounds on `fanout_workers` (`RunCreate`, ge=1, le=8). */
export const MIN_WORKERS = 1
export const MAX_WORKERS = 8

export const armKey = (arm: Arm): string => `${arm.agentMode}-${arm.contextMode}`

export const DEFAULT_RUN_SETTINGS: RunSettings = {
  armKey: armKey(DEFAULT_ARM),
  fanoutWorkers: 1,
}

export function armFor(settings: RunSettings): Arm {
  return ARMS.find((arm) => armKey(arm) === settings.armKey) ?? DEFAULT_ARM
}

export function clampWorkers(value: unknown): number {
  const n = Math.round(Number(value))
  if (!Number.isFinite(n)) return MIN_WORKERS
  return Math.min(MAX_WORKERS, Math.max(MIN_WORKERS, n))
}

export function isDefault(settings: RunSettings): boolean {
  return armFor(settings).isDefault === true
    && settings.fanoutWorkers === 1
}

/** The settings that differ from the default, in words, for a tooltip. */
export function describe(settings: RunSettings): string[] {
  const arm = armFor(settings)
  return [
    ...(arm.isDefault ? [] : [`${arm.agentMode}·${arm.contextMode}`]),
    ...(settings.fanoutWorkers > 1 ? [`${settings.fanoutWorkers} workers`] : []),
  ]
}

export interface RunOptions {
  agent_mode?: AgentMode
  context_mode?: ContextMode
  fanout_workers?: number
}

/**
 * The request body. A value at its default is LEFT OUT rather than sent:
 * `HarnessRunConfig` owns the defaults, and posting a copy of them from here
 * would be a second place they are written down. `undefined` when nothing
 * differs, so the default run posts no body at all.
 */
export function toRunOptions(settings: RunSettings): RunOptions | undefined {
  const arm = armFor(settings)
  const options: RunOptions = {
    ...(arm.isDefault ? {} : { agent_mode: arm.agentMode, context_mode: arm.contextMode }),
    ...(settings.fanoutWorkers > 1 ? { fanout_workers: settings.fanoutWorkers } : {}),
  }
  return Object.keys(options).length ? options : undefined
}

const STORAGE_KEY = 'agisd.runSettings'

/** Whatever is stored, coerced field by field; anything unreadable is the
 *  default. Storage can be absent or throw (private windows, blocked site
 *  data), and the page has to work the same without it. */
export function loadRunSettings(): RunSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_RUN_SETTINGS
    const stored = JSON.parse(raw) as Partial<RunSettings>
    const settings: RunSettings = {
      armKey: typeof stored.armKey === 'string' ? stored.armKey : DEFAULT_RUN_SETTINGS.armKey,
      fanoutWorkers: clampWorkers(stored.fanoutWorkers ?? 1),
    }
    // An arm key no longer in `ARMS` is the default arm, and is stored as such.
    return { ...settings, armKey: armKey(armFor(settings)) }
  } catch {
    return DEFAULT_RUN_SETTINGS
  }
}

export function saveRunSettings(settings: RunSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // Not remembered; the setting still applies to this page.
  }
}

export function useRunSettings(): [RunSettings, (next: RunSettings) => void] {
  const [settings, setSettings] = useState(loadRunSettings)
  useEffect(() => saveRunSettings(settings), [settings])
  return [settings, setSettings]
}
