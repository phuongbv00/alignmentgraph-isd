import { CircleCheck, FilePen } from 'lucide-react'
import type { BriefPreview } from '../api/types'

interface Props {
  preview: BriefPreview
  onOpen: () => void
  missingFields: string[]
  committedAt?: string | null
  /** Shown while a brief is still being assembled through the conversation. */
  draft?: boolean
}

/**
 * The committed design brief, as a summary card. Deliberately not the whole
 * thing: counts for the context and constraints sections rather than their
 * contents, and the first few goals. The rest is one click away in the
 * inspector.
 */
export function BriefCard({ preview, onOpen, missingFields, committedAt, draft }: Props) {
  const empty = !preview.title && !preview.domain && preview.learning_goals_total === 0

  return (
    <div className={`brief-card${draft ? ' draft' : ''}`} onClick={onOpen} role="button" tabIndex={0}
         onKeyDown={(e) => e.key === 'Enter' && onOpen()}>
      {empty ? (
        <div className="muted small">
          No design brief yet — describe the program in the chat below, or import a scenario file.
        </div>
      ) : (
        <>
          <div className="brief-card-head">
            <div className="brief-title">{preview.title || 'Untitled program'}</div>
            {draft ? (
              <span className="chip draft-chip icon-label"><FilePen size={11} /> Draft</span>
            ) : committedAt ? (
              <span
                className="chip committed-chip icon-label"
                title={new Date(committedAt).toLocaleString()}
              >
                <CircleCheck size={11} /> Committed
              </span>
            ) : null}
          </div>
          <div className="chips">
            {preview.id && <span className="chip mono">{preview.id}</span>}
            {preview.domain && <span className="chip">{preview.domain}</span>}
            {preview.difficulty && <span className="chip">{preview.difficulty}</span>}
            {preview.duration && <span className="chip">{preview.duration}</span>}
            {preview.target_audience && <span className="chip">{preview.target_audience}</span>}
            <span className="chip">
              context {preview.context_filled}/{preview.context_total}
            </span>
            <span className="chip">
              constraints {preview.constraints_filled}/{preview.constraints_total}
            </span>
          </div>

          {preview.learning_goals.length > 0 && (
            <ul className="goal-list">
              {preview.learning_goals.map((goal, index) => (
                <li key={index}>{goal}</li>
              ))}
              {preview.learning_goals_total > preview.learning_goals.length && (
                <li className="muted">
                  + {preview.learning_goals_total - preview.learning_goals.length} more
                </li>
              )}
            </ul>
          )}

          {preview.user_message && !preview.learning_goals.length && (
            <div className="small muted" style={{ marginTop: 6 }}>{preview.user_message}</div>
          )}

          {missingFields.length > 0 && (
            <div className="small muted" style={{ marginTop: 8 }}>
              Still unknown: {missingFields.join(', ')}
            </div>
          )}
        </>
      )}
    </div>
  )
}
