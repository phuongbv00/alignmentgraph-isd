import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { Check, ChevronDown, Circle, CircleCheck, CircleSlash, CircleX, Copy, Loader2, Play, RotateCw, Square } from 'lucide-react'
import type { RunStreamState } from '../state/useRunStream'
import { phaseLabel } from '../lib/phaseTimeline'
import { ARMS, DEFAULT_ARM, armOf, type Arm } from '../lib/arms'

interface Props {
  stream: RunStreamState
  canRun: boolean
  runDisabledReason: string
  onRun: (arm: Arm) => void
  onCancel: () => void
  starting: boolean
}

/**
 * Status, progress and the run controls.
 *
 * The elapsed counter matters more than it looks: a real run spends tens of
 * seconds inside a single model call with nothing else to report, and a
 * ticking timer under "waiting for the model" is the difference between
 * looking alive and looking hung.
 */
export function RunHeader({ stream, canRun, runDisabledReason, onRun, onCancel, starting }: Props) {
  const active = stream.status === 'running' || stream.status === 'cancelling'
  const elapsed = useElapsed(stream.llmStartedAt)
  const arm = armOf(stream.stats.agent_mode, stream.stats.context_mode)

  const progress = stream.phase && stream.phase.total
    ? Math.round(((stream.phase.index - 1) / stream.phase.total) * 100)
    : stream.status === 'succeeded' ? 100 : 0

  return (
    <div className="run-header">
      {stream.runId && <RunIdChip runId={stream.runId} />}

      <span className={`pill ${stream.status}`}>
        <StatusIcon status={stream.status} />
        {statusLabel(stream)}
      </span>

      {/* Shown for EVERY run that reports an arm, the default one included: a
          badge that appeared only on ablation runs would make its absence mean
          both "the default arm" and "a run recorded before this", which are
          different things. */}
      {arm && (
        <span className="pill arm" title={arm.label}>
          {arm.agentMode}·{arm.contextMode}
        </span>
      )}

      {active && (
        <>
          <div className="progress-track" title={`Step ${stream.phase?.index ?? 0} of ${stream.phase?.total ?? 0}`}>
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <span className="small muted" style={{ whiteSpace: 'nowrap' }}>
            {/* Usually about a second — the model call in flight is aborted —
                but it can take longer on a provider whose transport cannot be
                closed, so this does not promise a number. */}
            {stream.status === 'cancelling'
              ? 'Stopping…'
              : stream.phase
                ? `${phaseLabel(stream.phase.name)} (${stream.phase.index}/${stream.phase.total})`
                : 'Starting…'}
            {stream.llmStartedAt !== null && ` · ${elapsed}s`}
          </span>
        </>
      )}

      {!active && stream.status !== 'idle' && (
        <span className="small muted">
          {summarise(stream)}
        </span>
      )}

      <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
        {active ? (
          <button
            className="btn small danger icon-label"
            onClick={onCancel}
            disabled={stream.status === 'cancelling'}
          >
            <Square size={12} />
            {stream.status === 'cancelling' ? 'Cancelling…' : 'Cancel'}
          </button>
        ) : (
          <RunSplitButton
            canRun={canRun}
            starting={starting}
            idle={stream.status === 'idle'}
            disabledReason={runDisabledReason}
            onRun={onRun}
          />
        )}
      </div>
    </div>
  )
}

/**
 * Run, as one control with two segments.
 *
 * The left segment is the run button as it always was and always starts the
 * DEFAULT arm; the caret opens the other three cells of the ablation matrix.
 * Split rather than a mode the button remembers: which arm a run used is a
 * property of that run, and a button whose meaning depended on an earlier
 * choice would make "Rerun" ambiguous exactly when two arms are being compared.
 *
 * Local to this file, like `RunIdChip`: one call site, and the props it needs
 * are the ones `RunHeader` already has.
 */
function RunSplitButton({ canRun, starting, idle, disabledReason, onRun }: {
  canRun: boolean
  starting: boolean
  idle: boolean
  disabledReason: string
  onRun: (arm: Arm) => void
}) {
  const [open, setOpen] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const caret = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const disabled = !canRun || starting

  useEffect(() => {
    if (!open) return
    // `pointerdown`, not `click`: the menu has to be gone before the click
    // lands on whatever is underneath, or dismissing it over the tab strip
    // both closes the menu and changes the tab. The listener is attached after
    // the click that opened the menu, so it cannot close it immediately.
    const onDown = (event: PointerEvent) => {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        caret.current?.focus()
      }
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  // The menu is a way to start a run, so it closes when starting one stops
  // being possible — a run begun in another window makes `canRun` false under
  // an open menu.
  useEffect(() => { if (disabled) setOpen(false) }, [disabled])

  // Focus the first item on open, which is also what makes Escape's
  // return-to-caret well defined however the menu was opened.
  useEffect(() => {
    if (open) menu.current?.querySelector('button')?.focus()
  }, [open])

  const moveFocus = (event: ReactKeyboardEvent<HTMLDivElement>, delta: number) => {
    const items = Array.from(menu.current?.querySelectorAll('button') ?? [])
    if (items.length === 0) return
    const at = items.indexOf(document.activeElement as HTMLButtonElement)
    items[(at + delta + items.length) % items.length]?.focus()
    event.preventDefault()
  }

  return (
    <div className="split" ref={wrap}>
      <button
        className="btn small primary icon-label"
        onClick={() => onRun(DEFAULT_ARM)}
        disabled={disabled}
        title={runTitle(disabledReason, DEFAULT_ARM)}
      >
        {starting ? <Loader2 size={13} className="spin" /> : idle
          ? <Play size={13} /> : <RotateCw size={13} />}
        {starting ? 'Starting…' : idle ? 'Run' : 'Rerun'}
      </button>
      <button
        className="btn small primary split-caret"
        ref={caret}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            setOpen(true)
            event.preventDefault()
          }
        }}
        disabled={disabled}
        title={disabledReason || 'Run under another ablation arm'}
        aria-label="Choose an ablation arm"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <ChevronDown size={13} />
      </button>

      {open && (
        <div
          className="menu"
          role="menu"
          ref={menu}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') moveFocus(event, 1)
            else if (event.key === 'ArrowUp') moveFocus(event, -1)
          }}
        >
          <div className="menu-label muted">Run under…</div>
          {ARMS.map((arm) => (
            <button
              key={`${arm.agentMode}x${arm.contextMode}`}
              role="menuitem"
              className="menu-item"
              onClick={() => {
                // Closed first: `onRun` is async and flips `starting`, which
                // disables the control this menu hangs off.
                setOpen(false)
                onRun(arm)
              }}
            >
              {arm.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function runTitle(disabledReason: string, arm: Arm): string {
  return disabledReason || arm.label
}

/**
 * The id of the run on screen, short, with a click to copy it in full.
 *
 * A run is addressed by this id everywhere OUTSIDE the browser — the artifact
 * directory on disk (``programs/<program>/runs/<run>/``), every
 * ``/api/runs/{id}`` route, the SSE stream. Without it here there is no way to
 * tell which run is being shown, so reading the graph in the app and the
 * trajectory on disk means guessing by timestamp. Choosing BETWEEN runs is the
 * sidebar's job; this only names the one selected.
 */
function RunIdChip({ runId }: { runId: string }) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 1200)
    return () => clearTimeout(timer)
  }, [copied])

  // Reset when the header moves to a different run, or a stale "Copied" from
  // the previous one sits under the new id.
  useEffect(() => setCopied(false), [runId])

  const copy = () => {
    // Unavailable over plain http on a non-localhost host; the id is still
    // readable on screen and in the tooltip, so a failure is silent.
    void navigator.clipboard?.writeText(runId).then(() => setCopied(true), () => undefined)
  }

  // Copies the FULL id: the short form is for recognising a run, not for
  // pasting into a path.
  return (
    <button className="run-id mono" onClick={copy} title={`Run ${runId} — click to copy`}>
      {runId.slice(0, 8)}
      {copied ? <Check size={11} /> : <Copy size={11} />}
    </button>
  )
}

function StatusIcon({ status }: { status: RunStreamState['status'] }) {
  switch (status) {
    case 'running':
    case 'cancelling':
      return <Loader2 size={13} className="spin" />
    case 'succeeded':
      return <CircleCheck size={13} />
    case 'failed':
    case 'interrupted':
      return <CircleX size={13} />
    case 'cancelled':
      return <CircleSlash size={13} />
    default:
      return <Circle size={13} />
  }
}

function statusLabel(stream: RunStreamState): string {
  switch (stream.status) {
    case 'idle': return 'No run yet'
    case 'running': return 'Running'
    case 'cancelling': return 'Cancelling'
    case 'succeeded': return 'Finished'
    case 'failed': return 'Failed'
    case 'cancelled': return 'Cancelled'
    case 'interrupted': return 'Interrupted'
  }
}

function summarise(stream: RunStreamState): string {
  const { stats } = stream
  if (stream.status === 'failed' || stream.status === 'interrupted') return stream.error
  const parts: string[] = []
  if (stats.node_count) parts.push(`${stats.node_count} nodes, ${stats.edge_count} edges`)
  if (stats.objective_count) {
    parts.push(`${stats.aligned_objective_count ?? 0}/${stats.objective_count} objectives aligned`)
  }
  if (stats.duration_seconds) parts.push(`${Math.round(stats.duration_seconds)}s`)
  if (stats.llm_calls) parts.push(`${stats.llm_calls} model calls`)
  return parts.join(' · ')
}

function useElapsed(since: number | null): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (since === null) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [since])
  return since === null ? 0 : Math.max(0, Math.round((now - since) / 1000))
}
