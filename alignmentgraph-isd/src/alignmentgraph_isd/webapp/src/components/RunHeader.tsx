import { useEffect, useState } from 'react'
import { Check, Circle, CircleCheck, CircleSlash, CircleX, Copy, Loader2, Play, RotateCw, Square } from 'lucide-react'
import type { RunStreamState } from '../state/useRunStream'
import { phaseLabel } from '../lib/phaseTimeline'

interface Props {
  stream: RunStreamState
  canRun: boolean
  runDisabledReason: string
  onRun: () => void
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
          <button
            className="btn small primary icon-label"
            onClick={onRun}
            disabled={!canRun || starting}
            title={runDisabledReason}
          >
            {starting ? <Loader2 size={13} className="spin" /> : stream.status === 'idle'
              ? <Play size={13} /> : <RotateCw size={13} />}
            {starting ? 'Starting…' : stream.status === 'idle' ? 'Run' : 'Rerun'}
          </button>
        )}
      </div>
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
