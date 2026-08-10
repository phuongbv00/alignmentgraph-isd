import { Loader2, Plus, Settings2, Trash2 } from 'lucide-react'
import type { ProgramSummary } from '../api/types'

interface Props {
  programs: ProgramSummary[]
  activeId: string | null
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (program: ProgramSummary) => void
  onOpenSettings: () => void
  busy: boolean
  deletingId: string | null
  /** Empty when no usable model is configured. */
  modelName: string
}

export function ProgramSidebar({
  programs, activeId, onSelect, onCreate, onDelete, onOpenSettings, busy, deletingId, modelName,
}: Props) {
  return (
    <aside className="sidebar">
      <div className="panel-header">
        <span>Training programs</span>
        <button className="btn btn-icon small primary icon-label" onClick={onCreate} disabled={busy}>
          <Plus size={14} />
        </button>
      </div>

      <div className="scroll">
        {programs.length === 0 ? (
          <div className="empty">
            No programs yet.
            <br />
            Create one to describe a course, or import a scenario file.
          </div>
        ) : (
          programs.map((program) => {
            const running = program.latest_run?.status === 'running'
              || program.latest_run?.status === 'cancelling'
            const deleting = deletingId === program.id

            return (
              // A row rather than a button, so the delete control can live
              // inside it without nesting one button in another.
              <div
                key={program.id}
                className={`program${program.id === activeId ? ' active' : ''}`}
                onClick={() => onSelect(program.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => event.key === 'Enter' && onSelect(program.id)}
              >
                <div className="program-row">
                  <div className="program-title">{program.title}</div>
                  <button
                    className="program-delete btn-icon small"
                    // Deleting removes the run artifacts too, so it is refused
                    // while a run is still writing them.
                    disabled={running || deleting}
                    title={running ? 'Cannot delete while a run is in progress' : 'Delete this program'}
                    aria-label={`Delete ${program.title}`}
                    onClick={(event) => {
                      event.stopPropagation()
                      onDelete(program)
                    }}
                  >
                    {deleting ? <Loader2 size={14} className="spin" /> : <Trash2 size={14} />}
                  </button>
                </div>
                <div className="program-meta">
                  {program.brief_preview.domain && <span>{program.brief_preview.domain}</span>}
                  {program.brief_preview.learning_goals_total > 0 && (
                    <span>{program.brief_preview.learning_goals_total} goals</span>
                  )}
                  {program.latest_run && (
                    <span
                      className={`pill ${program.latest_run.status}`}
                      style={{ fontSize: 10, padding: '3px 6px' }}
                    >
                      {program.latest_run.status}
                    </span>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Always reachable, not only from the error banner: changing which model
          the agent runs on is a normal thing to do during a demo. */}
      <button className="sidebar-footer" onClick={onOpenSettings} title="Model settings">
        <span className="muted small icon-label"><Settings2 size={13} /> Model</span>
        <span className={`small${modelName ? ' mono' : ' muted'}`}>
          {modelName || 'not configured'}
        </span>
      </button>
    </aside>
  )
}
