import { Loader2, Plus, Settings2, Trash2 } from 'lucide-react'
import type { ProgramSummary, RunSummary } from '../api/types'
import { runStamp } from '../lib/time'

interface Props {
  programs: ProgramSummary[]
  activeId: string | null
  onSelect: (id: string) => void
  /** Runs of the ACTIVE program only, newest first — the API orders them. */
  runs: RunSummary[]
  activeRunId: string | null
  onSelectRun: (runId: string) => void
  onCreate: () => void
  onDelete: (program: ProgramSummary) => void
  onOpenSettings: () => void
  busy: boolean
  deletingId: string | null
  /** Empty when no usable model is configured. */
  modelName: string
}

export function ProgramSidebar({
  programs, activeId, onSelect, runs, activeRunId, onSelectRun,
  onCreate, onDelete, onOpenSettings, busy, deletingId, modelName,
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

            const expanded = program.id === activeId && runs.length > 0

            return (
              <div key={program.id} className="program-group">
              {/* A row rather than a button, so the delete control can live
                  inside it without nesting one button in another. */}
              <div
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
                  {program.latest_run && !expanded && (
                    <span
                      className={`pill ${program.latest_run.status}`}
                      style={{ fontSize: 10, padding: '3px 6px' }}
                    >
                      {program.latest_run.status}
                    </span>
                  )}
                </div>
              </div>

              {expanded && (
                <div className="run-list">
                  {runs.map((run) => (
                    <RunRow
                      key={run.id}
                      run={run}
                      active={run.id === activeRunId}
                      onSelect={() => onSelectRun(run.id)}
                    />
                  ))}
                </div>
              )}
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

/**
 * One run of a program, as its own row under that program.
 *
 * The id is what a run is called everywhere outside the browser — its artifact
 * directory, its ``/api/runs/{id}`` routes — so it leads, and the timestamp is
 * only there to tell two runs of the same design apart at a glance. Switching
 * to an older run is safe at any time, including while another is running: the
 * event stream is per-run and replays from the start, so going back to the
 * live one loses nothing.
 */
function RunRow({ run, active, onSelect }: {
  run: RunSummary
  active: boolean
  onSelect: () => void
}) {
  return (
    <button
      className={`run-row${active ? ' active' : ''}`}
      onClick={onSelect}
      title={`Run ${run.id}`}
    >
      <span className={`run-dot ${run.status}`} />
      <span className="mono run-row-id">{run.id.slice(0, 8)}</span>
      <span className="small muted run-row-time">{runStamp(run.started_at ?? run.created_at)}</span>
    </button>
  )
}
