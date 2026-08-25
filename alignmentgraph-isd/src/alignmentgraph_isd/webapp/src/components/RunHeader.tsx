import { useEffect, useState } from 'react'
import { Circle, CircleCheck, CircleSlash, CircleX, Loader2, Play, RotateCw, Square } from 'lucide-react'
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
