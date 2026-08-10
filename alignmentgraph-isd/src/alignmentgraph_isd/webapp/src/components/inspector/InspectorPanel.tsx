import { useEffect, useState } from 'react'
import {
  ArrowLeft, ArrowRight, Check, PanelRightClose, PanelRightOpen, X,
} from 'lucide-react'
import { api } from '../../api/client'
import { BriefDetail } from './BriefDetail'
import { Collapsible, JsonRoot, MaybeJson } from './JsonTree'
import type {
  AlignmentGraphPayload,
  Brief,
  DeepAction,
  GraphEdge,
  GraphNode,
  ObjectiveAlignment,
  RunEvent,
  Selection,
} from '../../api/types'

interface Props {
  selection: Selection
  brief: Brief
  graph: AlignmentGraphPayload | null
  runId: string | null
  collapsed: boolean
  onToggle: () => void
  onSelect: (selection: Selection) => void
}

/**
 * The detail pane. Everything clickable in the app resolves to one `Selection`,
 * and this switch is the only place that decides how each kind is rendered.
 */
export function InspectorPanel({
  selection, brief, graph, runId, collapsed, onToggle, onSelect,
}: Props) {
  if (collapsed) {
    return (
      <aside className="inspector collapsed">
        <button
          className="btn small btn-icon"
          onClick={onToggle}
          title="Show details"
          aria-label="Show details"
          style={{ margin: 10 }}
        >
          <PanelRightOpen size={15} />
        </button>
      </aside>
    )
  }

  return (
    <aside className="inspector">
      <div className="panel-header">
        <span>{title(selection)}</span>
        <button
          className="btn small btn-icon"
          onClick={onToggle}
          title="Hide details"
          aria-label="Hide details"
        >
          <PanelRightClose size={15} />
        </button>
      </div>
      <div className="scroll">
        <Body selection={selection} brief={brief} graph={graph} runId={runId} onSelect={onSelect} />
      </div>
    </aside>
  )
}

function title(selection: Selection): string {
  switch (selection.kind) {
    case 'brief': return 'Design brief'
    case 'graph-node': return 'Graph node'
    case 'graph-edge': return 'Alignment relation'
    case 'event': return 'Trajectory step'
    case 'action': return 'Agent action'
    case 'artifact': return 'Artifact'
    default: return 'Details'
  }
}

function Body({ selection, brief, graph, runId, onSelect }: Omit<Props, 'collapsed' | 'onToggle'>) {
  switch (selection.kind) {
    case 'brief':
      return <BriefDetail brief={brief} />
    case 'graph-node':
      return <NodeDetail runId={runId} nodeId={selection.id} graph={graph} onSelect={onSelect} />
    case 'graph-edge':
      return <EdgeDetail edge={selection.edge} graph={graph} onSelect={onSelect} />
    case 'event':
      return <EventDetail events={selection.events} />
    case 'action':
      return <ActionDetail actions={selection.actions} />
    case 'artifact':
      return <ArtifactDetail runId={runId} name={selection.id} />
    default:
      return (
        <div className="empty">
          Select the brief, a graph node, a relation or a trajectory step to see it in full.
        </div>
      )
  }
}

// ── graph node ───────────────────────────────────────────────────────────────

function NodeDetail({
  runId, nodeId, graph, onSelect,
}: {
  runId: string | null
  nodeId: string
  graph: AlignmentGraphPayload | null
  onSelect: (selection: Selection) => void
}) {
  const [node, setNode] = useState<GraphNode | null>(null)
  const [error, setError] = useState('')

  // Fetched on demand rather than shipped with the graph: a section node holds
  // an entire ADDIE section, which is most of a ~95 kB dump.
  useEffect(() => {
    let cancelled = false
    setNode(null)
    setError('')
    if (!runId) return
    api.getNode(runId, nodeId)
      .then((value) => { if (!cancelled) setNode(value) })
      .catch((exc) => { if (!cancelled) setError(String(exc.message ?? exc)) })
    return () => { cancelled = true }
  }, [runId, nodeId])

  const alignment = graph?.objective_alignment?.[nodeId]
  const incident = (graph?.edges ?? []).filter((e) => e.source === nodeId || e.target === nodeId)

  return (
    <div className="inspector-body">
      <div className="section-title">Node</div>
      <dl className="kv">
        <dt>Id</dt><dd className="mono">{nodeId}</dd>
        <dt>Type</dt><dd>{node?.type || graph?.nodes.find((n) => n.id === nodeId)?.type || '—'}</dd>
        <dt>Kind</dt>
        <dd>{nodeId.includes(':') ? 'element (one item)' : 'section (a whole ADDIE section)'}</dd>
      </dl>

      {alignment && <AlignmentFlags flags={alignment} />}

      {incident.length > 0 && (
        <>
          <div className="section-title">Relations ({incident.length})</div>
          {incident.map((edge, index) => (
            <button
              key={index}
              className="timeline-row"
              style={{ padding: '5px 0' }}
              onClick={() => onSelect({
                kind: 'graph-edge',
                id: `${edge.relation_id}|${edge.source}|${edge.target}|${edge.type}`,
                edge,
              })}
            >
              <div className="small icon-label">
                {edge.source === nodeId ? <ArrowRight size={12} /> : <ArrowLeft size={12} />}
                <span className="mono">{edge.type || 'rooted-in'}</span>{' '}
                <span className="muted">{edge.source === nodeId ? edge.target : edge.source}</span>
              </div>
            </button>
          ))}
        </>
      )}

      <div className="section-title">Content</div>
      {error && <div className="small muted">{error}</div>}
      {!node && !error && <div className="small muted">Loading…</div>}
      {node && <JsonRoot value={node.data} defaultOpenDepth={2} />}
    </div>
  )
}

function AlignmentFlags({ flags }: { flags: ObjectiveAlignment }) {
  return (
    <>
      <div className="section-title">Constructive alignment</div>
      <div className="flags">
        <Flag on={flags.measured} label="measured by an assessment" />
        <Flag on={flags.supported} label="supported by an activity" />
        <Flag on={flags.evaluated} label="evaluated summatively" />
        <Flag on={flags.bloom_ok} label="Bloom level consistent" />
      </div>
      <div className="small muted" style={{ marginTop: 6 }}>
        {flags.aligned
          ? 'Fully aligned: every leg of the objective is covered.'
          : 'Not fully aligned — one of the legs above is missing.'}
      </div>
    </>
  )
}

function Flag({ on, label }: { on: boolean; label: string }) {
  return (
    <span className={`flag ${on ? 'on' : 'off'}`}>
      {on ? <Check size={12} /> : <X size={12} />} {label}
    </span>
  )
}

// ── graph edge ───────────────────────────────────────────────────────────────

const MECHANISM_EXPLANATION: Record<string, string> = {
  id: 'Established by a matching identifier — the artifact names the objective it refers to.',
  type: 'Established by matching types — a plan realised by the artifacts of its kind.',
  provenance: 'Established by provenance — this artifact was generated from that one.',
}

function EdgeDetail({
  edge, graph, onSelect,
}: {
  edge: GraphEdge
  graph: AlignmentGraphPayload | null
  onSelect: (selection: Selection) => void
}) {
  const coverage = edge.relation_id ? graph?.relation_coverage?.[edge.relation_id] : undefined

  return (
    <div className="inspector-body">
      <div className="section-title">Relation</div>
      <dl className="kv">
        <dt>Relation</dt><dd className="mono">{edge.type || 'rooted-in (structural)'}</dd>
        {coverage && <><dt>Means</dt><dd>{coverage.label}</dd></>}
        <dt>From</dt>
        <dd>
          <button className="btn small" onClick={() => onSelect({ kind: 'graph-node', id: edge.source })}>
            {edge.source}
          </button>
        </dd>
        <dt>To</dt>
        <dd>
          <button className="btn small" onClick={() => onSelect({ kind: 'graph-node', id: edge.target })}>
            {edge.target}
          </button>
        </dd>
      </dl>

      {edge.established_by && (
        <>
          <div className="section-title">How it was established</div>
          <div className="small">{MECHANISM_EXPLANATION[edge.established_by] ?? edge.established_by}</div>
        </>
      )}

      {edge.rationale && (
        <>
          <div className="section-title">Rationale</div>
          <div className="small">{edge.rationale}</div>
        </>
      )}

      {edge.evidence && (
        <>
          <div className="section-title">Evidence</div>
          <div className="small mono">{edge.evidence}</div>
        </>
      )}

      {coverage && (
        <>
          <div className="section-title">Coverage of {edge.relation_id} across the run</div>
          <CoverageBar value={coverage.coverage} />
          {coverage.uncovered.length > 0 && (
            <div className="small muted" style={{ marginTop: 4 }}>
              Not covered: {coverage.uncovered.join(', ')}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export function CoverageBar({ value }: { value: number }) {
  const percent = Math.round((value ?? 0) * 100)
  const tone = percent >= 100 ? '' : percent > 0 ? 'partial' : 'empty'
  return (
    <div className="coverage-row">
      <div className="coverage-bar">
        <div className={`coverage-fill ${tone}`} style={{ width: `${percent}%` }} />
      </div>
      <span className="muted">{percent}%</span>
    </div>
  )
}

// ── trajectory step ──────────────────────────────────────────────────────────

/**
 * A trajectory row, shown exactly as the run recorded it.
 *
 * The prompt and output are the summaries the harness writes into the
 * trajectory, not a separate fuller copy — so what is on screen is what the
 * stored artifact contains, and a reader can trust the two match.
 *
 * `events` is what the row folded together; a run of node edits is one row
 * over many events.
 */
function EventDetail({ events }: { events: RunEvent[] }) {
  const event = events[events.length - 1]
  const prompt = event.payload.input_summary as string | undefined
  const output = event.payload.output_summary as string | undefined

  return (
    <div className="inspector-body">
      <div className="section-title">Step</div>
      <dl className="kv">
        <dt>Kind</dt><dd className="mono">{event.kind}</dd>
        <dt>Sequence</dt><dd>{events[0].seq}</dd>
        <dt>Time</dt><dd className="small">{new Date(events[0].ts).toLocaleTimeString()}</dd>
        {events.length > 1 && <><dt>Events</dt><dd>{events.length}</dd></>}
      </dl>

      {typeof prompt === 'string' && (
        // Folded by default: it is the brief restated, which is rarely what
        // someone opened the step to look at.
        <Collapsible title="Prompt given to the agent" defaultOpen={false} note={`${prompt.length} chars`}>
          <MaybeJson text={prompt} />
        </Collapsible>
      )}
      {typeof output === 'string' && (
        <Collapsible title="What it produced" note={`${output.length} chars`}>
          <MaybeJson text={output} />
        </Collapsible>
      )}

      <Collapsible title="Raw payload" defaultOpen={false}>
        <JsonRoot value={event.payload} defaultOpenDepth={2} />
      </Collapsible>
    </div>
  )
}

// ── deep-trajectory action ───────────────────────────────────────────────────

/**
 * One row of the deep trajectory, in full.
 *
 * Rows are often a collapsed run of the same kind of work, so this shows every
 * action behind the row rather than only the first — the whole reason to open
 * "read the graph 40×" is to see which 40 reads they were.
 */
function ActionDetail({ actions }: { actions: DeepAction[] }) {
  const first = actions[0]
  const traversals = actions.filter((a) => Array.isArray(a.hops) && a.hops.length > 0)

  return (
    <div className="inspector-body">
      <div className="section-title">Action</div>
      <dl className="kv">
        <dt>Kind</dt><dd className="mono">{first.kind}</dd>
        <dt>Agent</dt><dd>{first.actor || '(harness)'}</dd>
        <dt>Phase</dt><dd>{first.phase || '—'}</dd>
        <dt>At</dt><dd>{(Number(first.elapsed_ms) / 1000).toFixed(1)}s into the run</dd>
        {actions.length > 1 && <><dt>Folded</dt><dd>{actions.length} actions</dd></>}
      </dl>

      {traversals.map((action, index) => (
        <Collapsible key={index} title={`Relation walk: ${(action.rel_path ?? []).join(' → ')}`}>
          {(action.hops as any[]).map((hop, hopIndex) => (
            <div key={hopIndex} className="hop">
              <div className="hop-head small">
                hop {hopIndex + 1} via <span className="mono">{hop.edge_type}</span>
                {' '}— {hop.from.length} → {hop.to.length} nodes
              </div>
              {(hop.edges as { from: string; to: string }[]).map((edge, edgeIndex) => (
                <div key={edgeIndex} className="small mono muted">
                  {edge.from} → {edge.to}
                </div>
              ))}
            </div>
          ))}
        </Collapsible>
      ))}

      <Collapsible title={actions.length > 1 ? `All ${actions.length} actions` : 'Detail'}>
        <JsonRoot value={actions.length === 1 ? first : actions} defaultOpenDepth={2} />
      </Collapsible>
    </div>
  )
}

// ── artifact ─────────────────────────────────────────────────────────────────

function ArtifactDetail({ runId, name }: { runId: string | null; name: string }) {
  const [value, setValue] = useState<unknown>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setValue(null)
    setError('')
    if (!runId) return
    api.getArtifact(runId, name)
      .then((data) => { if (!cancelled) setValue(data) })
      .catch((exc) => { if (!cancelled) setError(String(exc.message ?? exc)) })
    return () => { cancelled = true }
  }, [runId, name])

  return (
    <div className="inspector-body">
      <div className="section-title">{name.replace(/_/g, ' ')}</div>
      {error && <div className="small muted">{error}</div>}
      {!value && !error && <div className="small muted">Loading…</div>}
      {value !== null && <JsonRoot value={value} defaultOpenDepth={2} />}
    </div>
  )
}
