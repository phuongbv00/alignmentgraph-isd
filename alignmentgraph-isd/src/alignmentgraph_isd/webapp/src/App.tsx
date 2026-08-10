import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { api } from './api/client'
import { BriefTab } from './components/BriefTab'
import { DeepTimeline } from './components/DeepTimeline'
import { GraphView } from './components/GraphView'
import { ModelSettings } from './components/ModelSettings'
import { ProgramSidebar } from './components/ProgramSidebar'
import { RunHeader } from './components/RunHeader'
import { TrajectoryTimeline } from './components/TrajectoryTimeline'
import { InspectorPanel } from './components/inspector/InspectorPanel'
import { useRunStream } from './state/useRunStream'
import type {
  AlignmentGraphPayload, DeepAction, DeepTrajectory, Health, ProgramDetail, ProgramSummary, Selection,
} from './api/types'

type Tab = 'chat' | 'trajectory' | 'graph'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [programs, setPrograms] = useState<ProgramSummary[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ProgramDetail | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('chat')
  const [selection, setSelection] = useState<Selection>({ kind: 'none' })
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [finishedGraph, setFinishedGraph] = useState<AlignmentGraphPayload | null>(null)
  const [finishedDeep, setFinishedDeep] = useState<DeepAction[]>([])

  const stream = useRunStream(runId)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [])

  const refreshPrograms = useCallback(async () => {
    setPrograms(await api.listPrograms())
  }, [])

  useEffect(() => { void refreshPrograms() }, [refreshPrograms])

  // Load a program, and attach to its most recent run so a page reload lands
  // back on whatever was happening.
  useEffect(() => {
    if (!activeId) {
      setDetail(null)
      setRunId(null)
      return
    }
    let cancelled = false
    api.getProgram(activeId).then((value) => {
      if (cancelled) return
      setDetail(value)
      setSelection({ kind: 'none' })
      setWarnings([])
      const latest = value.runs[0] ?? null
      setRunId(latest?.id ?? null)
      setTab(latest ? (latest.status === 'running' ? 'trajectory' : 'graph') : 'chat')
    }).catch((exc) => !cancelled && setError(String(exc.message ?? exc)))
    return () => { cancelled = true }
  }, [activeId])

  // A run that finished before this page loaded never streamed a graph frame,
  // so fetch the stored one.
  useEffect(() => {
    setFinishedGraph(null)
    if (!runId || stream.graph || stream.status === 'running' || stream.status === 'idle') return
    let cancelled = false
    api.getGraph(runId, 'light')
      .then((graph) => { if (!cancelled) setFinishedGraph(graph) })
      .catch(() => { /* a failed run may have no graph; the panel says so */ })
    return () => { cancelled = true }
  }, [runId, stream.status, stream.graph])

  // Refresh the sidebar whenever the run's status settles into something new,
  // so its badge and the program ordering catch up. `cancelling` is included
  // deliberately: the header switches to it immediately, and a sidebar badge
  // still reading "running" for the same run contradicts it on screen.
  useEffect(() => {
    if (stream.status === 'idle' || stream.status === 'running') return
    void refreshPrograms()
    if (activeId) api.getProgram(activeId).then(setDetail).catch(() => {})
  }, [stream.status, activeId, refreshPrograms])

  const graph = stream.graph ?? finishedGraph
  const deepActions = stream.actions.length > 0 ? stream.actions : finishedDeep

  // A run that finished before this page loaded streamed no actions, so read
  // the stored deep trajectory instead.
  useEffect(() => {
    setFinishedDeep([])
    if (!runId || stream.actions.length > 0 || stream.status === 'running' || stream.status === 'idle') {
      return
    }
    let cancelled = false
    api.getArtifact(runId, 'trajectory_deep')
      .then((doc) => {
        if (!cancelled) setFinishedDeep(((doc as DeepTrajectory)?.actions) ?? [])
      })
      .catch(() => { /* older runs have none; the event view covers them */ })
    return () => { cancelled = true }
  }, [runId, stream.status, stream.actions.length])

  const createProgram = async () => {
    setBusy(true)
    try {
      const created = await api.createProgram('')
      await refreshPrograms()
      setActiveId(created.program.id)
    } catch (exc) {
      setError(String((exc as Error).message))
    } finally {
      setBusy(false)
    }
  }

  const deleteProgram = async (program: ProgramSummary) => {
    // Confirmed because it also removes the run artifacts — the graph dumps and
    // trajectories — which nothing else in the app can bring back.
    const runs = program.latest_run ? ' and its runs' : ''
    if (!window.confirm(`Delete "${program.title}"${runs}? This cannot be undone.`)) return

    setDeletingId(program.id)
    setError('')
    try {
      await api.deleteProgram(program.id)
      if (activeId === program.id) setActiveId(null)
      await refreshPrograms()
    } catch (exc) {
      setError(String((exc as Error).message))
    } finally {
      setDeletingId(null)
    }
  }

  const sendMessage = async (content: string) => {
    if (!activeId) return
    const turn = await api.sendMessage(activeId, content)
    setDetail((current) => current && ({
      ...current,
      program: { ...current.program, brief_committed_at: turn.brief_committed_at },
      brief: turn.brief,
      brief_preview: turn.brief_preview,
      missing_fields: turn.missing_fields,
      messages: [...current.messages, turn.user_message, turn.assistant_message],
    }))
    setWarnings(turn.warnings)
    void refreshPrograms()
  }

  const commitBrief = async () => {
    if (!activeId) return
    setCommitting(true)
    setError('')
    try {
      const response = await api.commitBrief(activeId)
      setDetail((current) => current && ({
        ...current,
        program: { ...current.program, brief_committed_at: response.brief_committed_at ?? null },
        brief: response.brief,
        brief_preview: response.brief_preview,
        missing_fields: response.missing_fields,
      }))
      void refreshPrograms()
    } catch (exc) {
      setError(String((exc as Error).message))
    } finally {
      setCommitting(false)
    }
  }

  const importScenario = async (file: File) => {
    if (!activeId) return
    const response = await api.importBrief(activeId, file)
    setDetail((current) => current && ({
      ...current,
      // A file arrives whole, so it is the brief immediately — no commit step.
      program: { ...current.program, brief_committed_at: response.brief_committed_at },
      brief: response.brief,
      brief_preview: response.brief_preview,
      missing_fields: response.missing_fields,
    }))
    setWarnings(response.warnings)
    setSelection({ kind: 'brief' })
    void refreshPrograms()
  }

  const startRun = async () => {
    if (!activeId) return
    setStarting(true)
    setError('')
    try {
      const { run_id } = await api.startRun(activeId)
      setRunId(run_id)
      setTab('trajectory')
      void refreshPrograms()
    } catch (exc) {
      setError(String((exc as Error).message))
    } finally {
      setStarting(false)
    }
  }

  const cancelRun = async () => {
    if (!runId) return
    try {
      await api.cancelRun(runId)
    } catch (exc) {
      setError(String((exc as Error).message))
    }
  }

  const runActive = stream.status === 'running' || stream.status === 'cancelling'
  const modelMissing = health !== null && !health.llm_configured
  const canRun = Boolean(detail?.brief_preview.is_runnable) && !runActive && !modelMissing
  const runDisabledReason = modelMissing
    ? 'No model is configured on the server.'
    : !detail?.brief_preview.is_runnable
      ? 'Describe the program or import a scenario file first.'
      : ''

  const messages = useMemo(() => detail?.messages ?? [], [detail])

  return (
    <div className="app">
      <ProgramSidebar
        programs={programs}
        activeId={activeId}
        onSelect={setActiveId}
        onCreate={() => void createProgram()}
        onDelete={(program) => void deleteProgram(program)}
        onOpenSettings={() => setSettingsOpen(true)}
        busy={busy}
        deletingId={deletingId}
        modelName={health?.llm_configured ? health.model_name : ''}
      />

      <main className="main">
        {modelMissing && (
          <div className="banner">
            {/* The server's own diagnosis: "no model configured" and "the
                endpoint rejected the credentials" need different fixes. */}
            {health?.model_error || 'No model is configured.'}
            {' '}Runs and the planning conversation are unavailable until it is set up.{' '}
            <button className="btn small" onClick={() => setSettingsOpen(true)}>
              Configure the model
            </button>
          </div>
        )}
        {stream.status === 'interrupted' && (
          <div className="banner">
            This run was interrupted when the server restarted. Its partial output was kept; start
            a new run to finish the design.
          </div>
        )}
        {error && <div className="banner error">{error}</div>}

        {!detail ? (
          <div className="empty" style={{ margin: 'auto' }}>
            Select a training program on the left, or create one to begin.
          </div>
        ) : (
          <>
            <RunHeader
              stream={stream}
              canRun={canRun}
              runDisabledReason={runDisabledReason}
              onRun={() => void startRun()}
              onCancel={() => void cancelRun()}
              starting={starting}
            />

            <nav className="tabs">
              <button className={`tab${tab === 'chat' ? ' active' : ''}`} onClick={() => setTab('chat')}>
                Brief
              </button>
              <button className={`tab${tab === 'trajectory' ? ' active' : ''}`} onClick={() => setTab('trajectory')}>
                Trajectory{stream.events.length > 0 ? ` (${stream.events.length})` : ''}
              </button>
              <button className={`tab${tab === 'graph' ? ' active' : ''}`} onClick={() => setTab('graph')}>
                Graph{graph ? ` (${graph.nodes.length})` : ''}
              </button>
              {stream.status !== 'idle' && (
                <button
                  className="tab"
                  style={{ marginLeft: 'auto' }}
                  onClick={() => { setSelection({ kind: 'artifact', id: 'addie_output' }); setInspectorCollapsed(false) }}
                >
                  <span className="icon-label">ADDIE output <ArrowRight size={13} /></span>
                </button>
              )}
            </nav>

            <div className="tab-body">
              {tab === 'chat' && (
                <BriefTab
                  preview={detail.brief_preview}
                  missingFields={detail.missing_fields}
                  committedAt={detail.program.brief_committed_at}
                  messages={messages}
                  onSend={sendMessage}
                  onImport={importScenario}
                  onCommit={commitBrief}
                  onOpenBrief={() => { setSelection({ kind: 'brief' }); setInspectorCollapsed(false) }}
                  chatDisabled={modelMissing || runActive}
                  chatDisabledReason={
                    modelMissing ? 'No model configured.' : 'Wait for the current run to finish.'
                  }
                  warnings={warnings}
                  committing={committing}
                />
              )}
              {tab === 'trajectory' && (
                // The deep record when there is one — live, or reloaded for a
                // finished run. The event-based view remains for runs made
                // before the deep trajectory existed.
                deepActions.length > 0 ? (
                  <DeepTimeline
                    actions={deepActions}
                    selection={selection}
                    onSelect={(value) => { setSelection(value); setInspectorCollapsed(false) }}
                  />
                ) : (
                  <TrajectoryTimeline
                    events={stream.events}
                    selection={selection}
                    onSelect={(value) => { setSelection(value); setInspectorCollapsed(false) }}
                  />
                )
              )}
              {tab === 'graph' && (
                <GraphView
                  graph={graph}
                  graphRev={stream.graphRev}
                  selection={selection}
                  onSelect={(value) => { setSelection(value); setInspectorCollapsed(false) }}
                />
              )}
            </div>
          </>
        )}
      </main>

      <InspectorPanel
        selection={selection}
        brief={detail?.brief ?? {}}
        graph={graph}
        runId={runId}
        collapsed={inspectorCollapsed}
        onToggle={() => setInspectorCollapsed((value) => !value)}
        onSelect={setSelection}
      />

      {settingsOpen && (
        <ModelSettings
          onClose={() => setSettingsOpen(false)}
          onSaved={() => { api.health().then(setHealth).catch(() => {}) }}
        />
      )}
    </div>
  )
}
