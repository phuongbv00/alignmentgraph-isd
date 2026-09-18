import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { api } from './api/client'
import { BriefTab } from './components/BriefTab'
import { ContextGrid } from './components/ContextGrid'
import { ViolationGrid } from './components/ViolationGrid'
import { PhaseTimeline } from './components/PhaseTimeline'
import { GraphView } from './components/GraphView'
import { ModelSettings } from './components/ModelSettings'
import { ProgramSidebar } from './components/ProgramSidebar'
import { RunHeader } from './components/RunHeader'
import { InspectorPanel } from './components/inspector/InspectorPanel'
import { useRunStream } from './state/useRunStream'
import type { Arm } from './lib/arms'
import type {
  AgentContext, AlignmentGraphPayload, DeepAction, DeepTrajectory, Finding, Health, ProgramDetail, ProgramSummary, Selection,
} from './api/types'

type Tab = 'chat' | 'trajectory' | 'context' | 'violations' | 'graph'

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
  const [finishedFindings, setFinishedFindings] = useState<Finding[]>([])
  const [contexts, setContexts] = useState<AgentContext[]>([])

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
    // A prose run builds no graph and its `graph.json` is `{}`, which the graph
    // endpoint answers with an EMPTY payload rather than nothing. Fetched, that
    // reads on screen as a graph that failed to draw; left unfetched, the tab
    // keeps its empty state and `GraphView` can say why there is none.
    if (stream.stats.context_mode === 'prose') return
    let cancelled = false
    api.getGraph(runId, 'light')
      .then((graph) => { if (!cancelled) setFinishedGraph(graph) })
      .catch(() => { /* a failed run may have no graph; the panel says so */ })
    return () => { cancelled = true }
  }, [runId, stream.status, stream.graph, stream.stats.context_mode])

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
  // The live rows lead: they appear as each agent starts, while the fetched
  // transcripts only catch up at a phase boundary or at the end.
  const liveContextCount = Math.max(stream.contextRows.length, contexts.length)
  // The COUNT ON THE TAB is what is still open, not what was ever found: a run
  // that found twelve problems and fixed eleven is a good run, and a tab
  // reading "12" says the opposite.
  //
  // Shown for any run, INCLUDING zero. The other tabs hide a zero, but they are
  // never actually zero once a run is under way, so hiding it there costs
  // nothing; this one is legitimately zero — that is the outcome the design is
  // aiming at — and a bare "Violations" then reads as a tab that has not loaded
  // rather than as a clean run. It was already inconsistent with itself: a run
  // that found problems and repaired them all has `findings` yet zero open, so
  // it printed "(0)" while a run that found nothing printed nothing.
  // The stream wins whenever it has anything, and it is guaranteed to have the
  // SETTLED ledger by the end: `Memory.settle` runs inside the harness, its
  // frame goes out on the reconcile phase's exit, and the SSE follow loop
  // yields pending violations frames BEFORE it returns on a terminal run. The
  // fetched copy is what a reload or a replayed run gets.
  const findings = stream.findings.length > 0 ? stream.findings : finishedFindings
  const openFindings = findings.filter((f) => f.outcome === 'open').length
  const deepActions = stream.actions.length > 0 ? stream.actions : finishedDeep

  // A run that finished before this page loaded streamed no actions, so read
  // the stored deep trajectory instead — which is where they live once a run
  // ends: the server deletes its wire log at that point
  // (`artifacts.discard_events`), the artifacts being the record from then on.
  // So this is the normal path for any finished run, not a fallback for one
  // replayed after a restart.
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

  // Contexts arrive LIVE as rows (no transcripts) on the stream, the same way
  // the graph does: the harness republishes each context after every turn, so
  // the list fills in and its meters move while the agents are still working.
  //
  // The transcripts are fetched whole, and only at the points where a fetch is
  // worth its size: when the run ends, and at each phase boundary. Between
  // those the rows carry the list, and a row the reader opens shows the
  // transcript from the last fetch — which is why the row says how many turns
  // it has now, so a stale body is visible as stale rather than passing for
  // current.
  // Fetched once so a reload mid-run, and a finished run replayed from disk,
  // both start with what the ledger holds — `_live_or_persisted` answers from
  // live state while the run is in the registry and from violations.json after.
  // The stream takes over from there and needs no phase-boundary re-fetch the
  // way the contexts do: a violations frame carries the whole ledger, where a
  // context row carries only its head.
  useEffect(() => {
    setFinishedFindings([])
    if (!runId || stream.status === 'idle') return
    let cancelled = false
    api.getViolations(runId)
      .then((rows) => { if (!cancelled) setFinishedFindings(rows) })
      .catch(() => { /* older runs recorded none */ })
    return () => { cancelled = true }
  }, [runId, stream.status])

  useEffect(() => {
    setContexts([])
    if (!runId || stream.status === 'idle') return
    let cancelled = false
    api.getContexts(runId)
      .then((rows) => { if (!cancelled) setContexts(rows) })
      .catch(() => { /* older runs recorded none */ })
    return () => { cancelled = true }
  }, [runId, stream.status, stream.phase?.index])

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

  const startRun = async (arm: Arm, fullDevelopment = false) => {
    if (!activeId) return
    setStarting(true)
    setError('')
    try {
      // The default arm sends no override at all: `HarnessRunConfig` owns those
      // values, and posting a copy of them would be a second place they live.
      // Same for the development mode: only a run that asks for the whole
      // design to be written out says so.
      const options = {
        ...(arm.isDefault ? {} : { agent_mode: arm.agentMode, context_mode: arm.contextMode }),
        ...(fullDevelopment ? { development_mode: 'full' as const } : {}),
      }
      const { run_id } = await api.startRun(
        activeId, Object.keys(options).length ? options : undefined)
      setRunId(run_id)
      setTab('trajectory')
      void refreshPrograms()
      // Put the new run in the picker now. The status-settle effect below only
      // refetches once a run ENDS, so without this the list would omit the run
      // being watched for its whole duration.
      api.getProgram(activeId).then(setDetail).catch(() => {})
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
  // Not the same question as `runActive`: the reader can select a finished run
  // while a newer one is still going, and the Run button asks whether the
  // PROGRAM is busy, not whether the run on screen is.
  const programBusy = runActive || detail?.runs.some(
    (run) => run.status === 'running' || run.status === 'cancelling',
  ) === true
  const modelMissing = health !== null && !health.llm_configured
  const canRun = Boolean(detail?.brief_preview.is_runnable) && !programBusy && !modelMissing
  const runDisabledReason = modelMissing
    ? 'No model is configured on the server.'
    : !detail?.brief_preview.is_runnable
      ? 'Describe the program or import a scenario file first.'
      : programBusy && !runActive
        ? 'Another run of this program is still in progress.'
        : ''

  const messages = useMemo(() => detail?.messages ?? [], [detail])

  return (
    <div className="app">
      <ProgramSidebar
        programs={programs}
        activeId={activeId}
        onSelect={setActiveId}
        runs={detail?.runs ?? []}
        activeRunId={runId}
        onSelectRun={setRunId}
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
              onRun={(arm, fullDevelopment) => void startRun(arm, fullDevelopment)}
              onCancel={() => void cancelRun()}
              starting={starting}
            />

            <nav className="tabs">
              <button className={`tab${tab === 'chat' ? ' active' : ''}`} onClick={() => setTab('chat')}>
                Brief
              </button>
              <button className={`tab${tab === 'trajectory' ? ' active' : ''}`} onClick={() => setTab('trajectory')}>
                Trajectory{deepActions.length > 0 ? ` (${deepActions.length})` : ''}
              </button>
              <button className={`tab${tab === 'context' ? ' active' : ''}`} onClick={() => setTab('context')}>
                Context{liveContextCount > 0 ? ` (${liveContextCount})` : ''}
              </button>
              <button className={`tab${tab === 'violations' ? ' active' : ''}`} onClick={() => setTab('violations')}>
                Violations{stream.status !== 'idle' ? ` (${openFindings})` : ''}
              </button>
              <button className={`tab${tab === 'graph' ? ' active' : ''}`} onClick={() => setTab('graph')}>
                Graph{graph ? ` (${graph.nodes.length})` : ''}
              </button>
              {stream.status !== 'idle' && (
                <>
                  {/* The run's own facts — which arms it ran under, the turn
                      and submit counters, token totals, the residual audit.
                      Every tab beside it is about the DESIGN; nothing else in
                      the app says what the run itself did, so a question like
                      "did this stage run out of turns" was answerable only by
                      reading scattered error rows in the trajectory. */}
                  <button
                    className="tab"
                    style={{ marginLeft: 'auto' }}
                    onClick={() => { setSelection({ kind: 'artifact', id: 'metadata' }); setInspectorCollapsed(false) }}
                  >
                    <span className="icon-label">Run details <ArrowRight size={13} /></span>
                  </button>
                  <button
                    className="tab"
                    onClick={() => { setSelection({ kind: 'artifact', id: 'addie_output' }); setInspectorCollapsed(false) }}
                  >
                    <span className="icon-label">ADDIE output <ArrowRight size={13} /></span>
                  </button>
                </>
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
                <PhaseTimeline
                  actions={deepActions}
                  runId={runId}
                  runStarted={stream.status !== 'idle'}
                  runActive={runActive}
                  selection={selection}
                  onSelect={(value) => { setSelection(value); setInspectorCollapsed(false) }}
                  relations={graph?.relation_coverage}
                />
              )}
              {tab === 'violations' && (
                <ViolationGrid findings={findings} runId={runId} runActive={runActive}
                                relations={graph?.relation_coverage} />
              )}
              {tab === 'context' && (
                <ContextGrid contexts={contexts} rows={stream.contextRows} runId={runId} />
              )}
              {tab === 'graph' && (
                <GraphView
                  graph={graph}
                  graphRev={stream.graphRev}
                  runId={runId}
                  contextMode={stream.stats.context_mode}
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
        findings={findings}
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
