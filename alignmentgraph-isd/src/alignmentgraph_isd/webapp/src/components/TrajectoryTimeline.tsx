import { useMemo } from 'react'
import { mergeTimeline } from '../lib/mergeTimeline'
import type { RunEvent, Selection } from '../api/types'

interface Props {
  events: RunEvent[]
  selection: Selection
  onSelect: (selection: Selection) => void
}

export function TrajectoryTimeline({ events, selection, onSelect }: Props) {
  const rows = useMemo(() => mergeTimeline(events), [events])

  if (rows.length === 0) {
    return (
      <div className="empty">
        Nothing to show yet. Start a run and the agent's steps appear here as they happen.
      </div>
    )
  }

  const selectedId = selection.kind === 'event' ? selection.id : null

  return (
    <div className="scroll">
      <div className="timeline">
        {rows.map((row) => (
          <button
            key={row.id}
            className={[
              'timeline-row',
              row.kind === 'phase' ? 'phase' : '',
              row.tone ?? '',
              selectedId === row.id ? 'selected' : '',
            ].filter(Boolean).join(' ')}
            onClick={() => onSelect({ kind: 'event', id: row.id, events: row.events })}
          >
            <div className="timeline-title">{row.title}</div>
            {row.detail && <div className="timeline-detail">{row.detail}</div>}
          </button>
        ))}
      </div>
    </div>
  )
}
