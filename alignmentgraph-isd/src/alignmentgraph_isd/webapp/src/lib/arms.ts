import type { AgentMode, ContextMode } from '../api/types'

/**
 * The 2x2 ablation matrix, in the words the study reports it in.
 *
 * A cell is named by its two axes and nothing else. The benchmark's own
 * `A0`..`A3` codes are deliberately absent: they are a reporting vocabulary
 * owned by another repository, they say nothing to someone reading this app,
 * and mirroring them here would be a table to keep in step by hand.
 *
 * What is written here is a LABEL, not a request: starting the default arm
 * sends no override at all, so `config.py::HarnessRunConfig` stays the one
 * place the defaults live and the badge on a run reads what the server
 * actually resolved.
 */
export interface Arm {
  agentMode: AgentMode
  contextMode: ContextMode
  label: string
  isDefault?: boolean
}

export const ARMS: Arm[] = [
  {
    agentMode: 'multi',
    contextMode: 'graph',
    isDefault: true,
    label: 'Multi-agent x Graph context',
  },
  {
    agentMode: 'multi',
    contextMode: 'prose',
    label: 'Multi-agent x Prose context',
  },
  {
    agentMode: 'single',
    contextMode: 'graph',
    label: 'Single-agent x Graph context',
  },
  {
    agentMode: 'single',
    contextMode: 'prose',
    label: 'Single-agent x Prose context',
  },
]

export const DEFAULT_ARM: Arm = ARMS[0]

/**
 * The arm a run reports it ran under, or null when it does not say.
 *
 * A run recorded before the axes were carried in `stats` has neither field, and
 * that is a different thing from having run under the default — so it gets no
 * badge rather than an assumed one.
 */
export function armOf(agentMode?: string, contextMode?: string): Arm | null {
  return ARMS.find((arm) => arm.agentMode === agentMode && arm.contextMode === contextMode) ?? null
}
