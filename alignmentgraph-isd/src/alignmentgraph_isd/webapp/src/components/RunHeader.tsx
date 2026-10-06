import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { Check, Circle, CircleCheck, CircleSlash, CircleX, Copy, Loader2, Play, RotateCw, Settings, Square } from 'lucide-react'
import type { RunStreamState } from '../state/useRunStream'
import { phaseLabel } from '../lib/phaseTimeline'
import { ARMS, armOf } from '../lib/arms'
import {
  DEFAULT_RUN_SETTINGS, MAX_WORKERS, MIN_WORKERS, armFor, armKey, clampWorkers, describe,
  useRunSettings, type RunSettings,
} from '../lib/runSettings'

interface Props {
  stream: RunStreamState
  canRun: boolean
  runDisabledReason: string
  onRun: (settings: RunSettings) => void
  onCancel: () => void
  starting: boolean
}

/**
 * Status, progress and the run controls.
 *
 * The elapsed counter matters more than it looks: a real run spends tens of
 * seconds inside a single model call with nothing else to report, and a timer
 * ticking beside the phase is the difference between looking alive and looking
 * hung. It counts the WHOLE run, which is also the number a reader compares
 * against the one a finished run reports.
 */
export function RunHeader({ stream, canRun, runDisabledReason, onRun, onCancel, starting }: Props) {
  const active = stream.status === 'running' || stream.status === 'cancelling'
  const elapsed = useElapsed(active ? stream.startedAt : null)
  const arm = armOf(stream.stats.agent_mode, stream.stats.context_mode)
  const [settings, setSettings] = useRunSettings()

  const progress = stream.phase && stream.phase.total
    ? Math.round(((stream.phase.index - 1) / stream.phase.total) * 100)
    : stream.status === 'succeeded' ? 100 : 0

  const note = active
    ? (stream.status === 'cancelling'
      // Usually about a second — the model call in flight is aborted — but
      // it can take longer on a provider whose transport cannot be closed, so
      // this does not promise a number.
      ? 'Stopping…'
      : stream.phase
        ? `${phaseLabel(stream.phase.name)} (${stream.phase.index}/${stream.phase.total})`
        : 'Starting…')
      + (stream.startedAt !== null ? ` · ${formatElapsed(elapsed)}` : '')
    : stream.status !== 'idle' ? summarise(stream) : ''

  return (
    <div className="run-header">
      {/* What the run IS, where it has got to, and the one control that acts on
          it. Everything but the phase line is short and fixed-width, so the
          control keeps its place whatever the pane is: the phase line takes
          what is left and is ellipsed, and the badges wrap under it rather than
          pushing it out of view. */}
      <div className="run-header-line">
        <div className="run-meta">
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

          {/* Only when it was asked for. This one confused two runs in a row:
              the option is chosen behind a menu and changes nothing a reader
              can see in the output, so the run has to say it out loud. */}
          {(stream.stats.fanout_workers ?? 1) > 1 && (
            <span
              className="pill arm"
              title={`${stream.stats.fanout_workers} of one family's Developers ran at once. `
                + 'Wall time only — the graph and the artifacts are identical.'}
            >
              worker×{stream.stats.fanout_workers}
            </span>
          )}

          {/* Beside the status while the run is going: it changes every few
              seconds and is the thing being watched. A finished run's summary is
              a different kind of line — long, read once — and gets its own band
              below. */}
          {active && <span className="small muted run-note" title={note}>{note}</span>}
        </div>

        <div className="run-actions">
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
            <>
              <RunButton
                settings={settings}
                canRun={canRun}
                starting={starting}
                idle={stream.status === 'idle'}
                disabledReason={runDisabledReason}
                onRun={onRun}
              />
              <RunSettingsMenu settings={settings} onChange={setSettings} />
            </>
          )}
        </div>
      </div>

      {active && (
        <div className="progress-track" title={`Step ${stream.phase?.index ?? 0} of ${stream.phase?.total ?? 0}`}>
          <div className="progress-fill" style={{ width: `${progress}%` }} />
        </div>
      )}

      {/* How the run ended, in one line: a list of counts, or an exception
          message, either of which can run to any length. */}
      {!active && note && (
        <div className="run-header-line">
          <span className="small muted run-note" title={note}>{note}</span>
        </div>
      )}
    </div>
  )
}

/**
 * Run, as it always was: one press starts a run under the current settings.
 *
 * The settings sit in their own menu beside it rather than inside a menu of
 * this button, because choosing a setting and starting a run are different
 * acts — a menu whose items started runs made "pick an arm" and "go" the same
 * click, and put tick boxes beside them that applied to nothing until one of
 * those items was pressed. The tooltip names every setting that is not the
 * default, since a setting behind a closed menu is one the reader cannot see.
 */
function RunButton({ settings, canRun, starting, idle, disabledReason, onRun }: {
  settings: RunSettings
  canRun: boolean
  starting: boolean
  idle: boolean
  disabledReason: string
  onRun: (settings: RunSettings) => void
}) {
  const arm = armFor(settings)
  const changed = describe(settings)
  return (
    <button
      className="btn small primary icon-label"
      onClick={() => onRun(settings)}
      disabled={!canRun || starting}
      title={disabledReason || (changed.length === 0 ? arm.label : `${arm.label} — ${changed.join(', ')}`)}
    >
      {starting ? <Loader2 size={13} className="spin" /> : idle
        ? <Play size={13} /> : <RotateCw size={13} />}
      {starting ? 'Starting…' : idle ? 'Run' : 'Rerun'}
    </button>
  )
}

/**
 * What the next run is started under, remembered in this browser.
 *
 * Remembering is safe where it would not be for the run itself: what a run WAS
 * is recorded on that run and shown in its badges from the server's resolved
 * values, so a setting changed here never relabels an earlier run. The dot on
 * the closed menu says that something is not the default.
 */
function RunSettingsMenu({ settings, onChange }: {
  settings: RunSettings
  onChange: (next: RunSettings) => void
}) {
  const [open, setOpen] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const changed = describe(settings)
  const current = armFor(settings)

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
        trigger.current?.focus()
      }
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  // Focus the first item on open, which is also what makes Escape's
  // return-to-trigger well defined however the menu was opened.
  useEffect(() => {
    if (open) menu.current?.querySelector<HTMLElement>('.menu-item')?.focus()
  }, [open])

  const moveFocus = (event: ReactKeyboardEvent<HTMLDivElement>, delta: number) => {
    // Inside the number field the arrows change the number.
    if ((event.target as HTMLElement).tagName === 'INPUT') return
    const items = Array.from(menu.current?.querySelectorAll<HTMLElement>('.menu-item') ?? [])
    if (items.length === 0) return
    const at = items.indexOf(document.activeElement as HTMLElement)
    items[(at + delta + items.length) % items.length]?.focus()
    event.preventDefault()
  }

  return (
    <div className="menu-anchor" ref={wrap}>
      <button
        className="btn btn-icon small icon-label"
        ref={trigger}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            setOpen(true)
            event.preventDefault()
          }
        }}
        title={changed.length > 0 ? `Run settings — ${changed.join(', ')}` : 'Run settings'}
        data-changed={changed.length > 0 ? 'on' : undefined}
        aria-label="Run settings"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Settings size={14} />
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
          {ARMS.map((arm) => {
            const selected = armKey(arm) === armKey(current)
            return (
              <button
                key={armKey(arm)}
                role="menuitemradio"
                aria-checked={selected}
                className="menu-item menu-radio"
                onClick={() => onChange({ ...settings, armKey: armKey(arm) })}
              >
                <span className="menu-check">{selected && <Check size={12} />}</span>
                {arm.label}
              </button>
            )
          })}
          <div className="menu-sep" role="separator" />
          <label
            className="menu-item menu-number"
            title={'How many of one family\'s Developers run at the same time; 1 runs them one after another. '
              + 'Same graph, same calls, same artifacts — wall time only. A family has about one work set '
              + 'per module, so more workers than modules buys nothing. Do not raise it on a shared or '
              + 'rate-limited endpoint: it buys HTTP 429s instead of time.'}
          >
            Developer workers
            <input
              type="number"
              min={MIN_WORKERS}
              max={MAX_WORKERS}
              step={1}
              value={settings.fanoutWorkers}
              onChange={(event) =>
                onChange({ ...settings, fanoutWorkers: clampWorkers(event.target.value) })}
            />
          </label>
          {changed.length > 0 && (
            <>
              <div className="menu-sep" role="separator" />
              <button
                role="menuitem"
                className="menu-item muted"
                onClick={() => onChange(DEFAULT_RUN_SETTINGS)}
              >
                Reset to defaults
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
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
  // The same clock the running header shows, so the two read as one number
  // observed twice rather than two measurements.
  if (stats.duration_seconds) parts.push(formatElapsed(Math.round(stats.duration_seconds)))
  if (stats.llm_calls) parts.push(`${stats.llm_calls} model calls`)
  return parts.join(' · ')
}

/** How long a run has taken, wherever the header says so: seconds under a
 *  minute, `m:ss` above it. A run is minutes long and three digits of seconds
 *  is a number the reader has to divide. */
function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
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
