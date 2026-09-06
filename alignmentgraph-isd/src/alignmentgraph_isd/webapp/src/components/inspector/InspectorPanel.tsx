import { useEffect, useState } from 'react'
import {
  ArrowLeft, ArrowRight, Check, PanelRightClose, PanelRightOpen, X,
} from 'lucide-react'
import { api } from '../../api/client'
import { BriefDetail } from './BriefDetail'
import { Collapsible, JsonRoot } from './JsonTree'
import { violationLabel } from '../../lib/violations'
import type {
  AlignmentGraphPayload,
  Brief,
  DeepAction,
  Finding,
  GraphEdge,
  GraphNode,
  ObjectiveAlignment,
  PlanRecord,
  Selection,
  WorkSet,
} from '../../api/types'

interface Props {
  selection: Selection
  brief: Brief
  graph: AlignmentGraphPayload | null
  /** The run's ledger, so a node's failed checks can show their own words
   *  rather than a type name. Empty while a run is going — a finding's outcome
   *  is not known until the last look settles it — which is why the FAILED
   *  LIST comes from the graph and only the wording comes from here. */
  findings: Finding[]
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
  selection, brief, graph, findings, runId, collapsed, onToggle, onSelect,
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
        <Body selection={selection} brief={brief} graph={graph} findings={findings}
              runId={runId} onSelect={onSelect} />
      </div>
    </aside>
  )
}

function title(selection: Selection): string {
  switch (selection.kind) {
    case 'brief': return 'Design brief'
    case 'graph-node': return 'Graph node'
    case 'graph-edge': return 'Alignment relation'
    case 'action': return 'Agent action'
    case 'artifact': return 'Artifact'
    default: return 'Details'
  }
}

function Body({ selection, brief, graph, findings, runId, onSelect }: Omit<Props, 'collapsed' | 'onToggle'>) {
  switch (selection.kind) {
    case 'brief':
      return <BriefDetail brief={brief} />
    case 'graph-node':
      return (
        <NodeDetail runId={runId} nodeId={selection.id} graph={graph}
                    findings={findings} onSelect={onSelect} />
      )
    case 'graph-edge':
      return <EdgeDetail edge={selection.edge} graph={graph} onSelect={onSelect} />
    case 'action':
      return <ActionDetail actions={selection.actions} runId={runId} />
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
  runId, nodeId, graph, findings, onSelect,
}: {
  runId: string | null
  nodeId: string
  graph: AlignmentGraphPayload | null
  findings: Finding[]
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

      <FailedChecks
        nodeId={nodeId}
        types={graph?.node_violations?.[nodeId] ?? []}
        findings={findings}
        // An objective's four alignment legs are already drawn above as
        // flags; repeating them here would say the same thing twice in two
        // shapes. Everything ELSE that failed on it — a vague statement, a
        // Bloom verb that disagrees with its level, a passive-only practice —
        // had nowhere to appear at all.
        skip={alignment ? OBJECTIVE_FLAG_TYPES : []}
      />

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

//: The checks `AlignmentFlags` already draws, so `FailedChecks` does not
//: repeat them for an objective.
const OBJECTIVE_FLAG_TYPES = [
  'C2', 'C3', 'bloom_mismatch_assessment', 'bloom_mismatch_activity',
]

/**
 * What is wrong with THIS node, whatever kind it is.
 *
 * Objectives had `AlignmentFlags`; every other node had an amber dashed
 * border and nothing else — a reader could see that an activity or an item was
 * flagged and had no way to learn why without opening the trajectory. The
 * border is drawn from the same `node_violations` map this reads, so the two
 * cannot disagree about which nodes are marked.
 *
 * The LIST comes from the graph (live, types only); the WORDING comes from the
 * run's ledger when it has settled. So a node shows its failed checks by name
 * during the run and gains the check's own message and repair hint at the end.
 */
function FailedChecks({ nodeId, types, findings, skip }: {
  nodeId: string
  types: string[]
  findings: Finding[]
  skip: string[]
}) {
  const shown = types.filter((type) => !skip.includes(type))
  if (shown.length === 0) return null
  const said = new Map(
    findings.filter((f) => f.node_id === nodeId).map((f) => [f.type, f]),
  )
  return (
    <>
      <div className="section-title">Failed checks ({shown.length})</div>
      <div className="flags">
        {shown.map((type) => <Flag key={type} on={false} label={violationLabel(type)} />)}
      </div>
      {shown.map((type) => {
        const finding = said.get(type)
        if (!finding) return null
        return (
          <div key={type} className="vg-note">
            {finding.messages.map((message, i) => (
              <p key={i} className="vg-message">{message}</p>
            ))}
            {finding.repair_hint && <p className="vg-hint">{finding.repair_hint}</p>}
          </div>
        )
      })}
    </>
  )
}

function AlignmentFlags({ flags }: { flags: ObjectiveAlignment }) {
  return (
    <>
      <div className="section-title">Constructive alignment</div>
      {/* Mirrors viz.objective_annotations: measured = C2 assessed_by,
          supported = C3 practiced_by. There is no rubric leg since
          2026-09-02 — a criterion is a field of the item that measures the
          objective, so it was true whenever `measured` was. An archived run
          still carries the flag and is still shown its own answer. */}
      <div className="flags">
        <Flag on={flags.measured} label="assessed by an assessment task (C2)" />
        <Flag on={flags.supported} label="practiced by an activity (C3)" />
        {flags.evaluated !== undefined && (
          <Flag on={flags.evaluated} label="scored by a rubric criterion (C7, retired)" />
        )}
        {/* Two flags, not one. `bloom_ok` was the conjunction of these, so a
          reader saw "Bloom level consistent ✗" and had to open the trajectory
          to learn WHICH of the two rules failed — the question that produced
          the whole violation ledger. `??` keeps an archived run rendering. */}
      <Flag on={flags.bloom_assessment_ok ?? flags.bloom_ok}
            label="assessed at its own Bloom level (C2)" />
      <Flag on={flags.bloom_activity_ok ?? flags.bloom_ok}
            label="practiced at its own Bloom level (C3)" />
      {(flags.bloom_notes ?? []).map((note, i) => (
        <div key={i} className="muted small vg-note">{note}</div>
      ))}
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


// ── deep-trajectory action ───────────────────────────────────────────────────

/**
 * One row of the deep trajectory, in full.
 *
 * Rows are often a collapsed run of the same kind of work, so this shows every
 * action behind the row rather than only the first — the whole reason to open
 * "read the graph 40×" is to see which 40 reads they were.
 */
function ActionDetail({ actions, runId }: { actions: DeepAction[]; runId: string | null }) {
  const first = actions[0]
  const context = first.context
  const traversals = actions.filter((a) => Array.isArray(a.context.hops) && a.context.hops.length > 0)
  const plans = actions.filter((a) => a.action === 'dev_plan')

  return (
    <div className="inspector-body">
      <div className="section-title">Action</div>
      <dl className="kv">
        <dt>Action</dt><dd className="mono">{first.action}</dd>
        <dt>Agent</dt><dd>{first.agent || '(harness)'}</dd>
        <dt>Phase</dt><dd>{String(context.phase ?? '—')}</dd>
        <dt>Recorded</dt><dd>{new Date(first.timestamp).toLocaleString()}</dd>
        {actions.length > 1 && <><dt>Occurrences</dt><dd>{actions.length} actions</dd></>}
      </dl>

      {plans.length > 0 && <PlanDetail runId={runId} actions={plans} />}

      {traversals.map((action, index) => (
        <Collapsible key={index} title={`Relation walk: ${(action.context.rel_path ?? []).join(' → ')}`}>
          {(action.context.hops as any[]).map((hop, hopIndex) => (
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

// ── work-set plans ───────────────────────────────────────────────────────────

/**
 * What the Developers were actually asked for.
 *
 * The `dev_plan` action carries a SUMMARY of the division — the set ids and
 * their objectives, where the plan came from, what the harness dropped or split
 * — which is what the timeline reads. The plan itself is the other half: the
 * pairs, the block theme, the instrument hint, the count each set was scoped
 * to. It lives in `plans.json`, so it is fetched here rather than carried on
 * every action.
 *
 * Joined on SET IDS, not on family: the event does not record its round, and a
 * replan round's ids carry it (`AS-01R1`), so matching by family alone would
 * show round 0's sets under round 1's beat.
 */
function PlanDetail({ runId, actions }: { runId: string | null; actions: DeepAction[] }) {
  const [plans, setPlans] = useState<PlanRecord[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setPlans(null)
    setError('')
    if (!runId) return
    api.getArtifact(runId, 'plans')
      .then((value) => { if (!cancelled) setPlans((value as PlanRecord[]) ?? []) })
      // Written when the run ends, like every other artifact: mid-run this is
      // a 409 and the event's own summary below is what there is.
      .catch((exc) => { if (!cancelled) setError(String(exc.message ?? exc)) })
    return () => { cancelled = true }
  }, [runId])

  const matched = (plans ?? []).length > 0
    ? actions.map((action) => [action, matchingPlan(plans ?? [], action)] as const)
    : []

  return (
    <>
      <div className="section-title">Work sets</div>
      {!plans && !error && <div className="small muted">Loading…</div>}
      {error && <div className="small muted">{error}</div>}
      {plans && matched.every(([, plan]) => plan === null) && !error && (
        <div className="small muted">
          This run recorded no plan for these sets. The event's own summary is
          under Detail below.
        </div>
      )}
      {matched.map(([action, plan], index) =>
        plan === null ? null : <PlanCard key={index} plan={plan} action={action} />)}
    </>
  )
}

function matchingPlan(plans: PlanRecord[], action: DeepAction): PlanRecord | null {
  const ids = new Set(
    ((action.context.sets as { set_id?: string }[] | undefined) ?? [])
      .map((entry) => entry.set_id)
      .filter(Boolean),
  )
  if (ids.size === 0) return null
  return plans.find((plan) => plan.work_sets.some((set) => ids.has(set.set_id))) ?? null
}

function PlanCard({ plan, action }: { plan: PlanRecord; action: DeepAction }) {
  return (
    <div style={{ marginTop: 8 }}>
      <dl className="kv">
        <dt>Family</dt><dd>{plan.family}</dd>
        <dt>Divided by</dt>
        <dd>
          {plan.source === 'llm' ? 'the Designer’s own dev plan'
            : plan.source === 'fallback' ? 'the deterministic split (no usable dev plan)'
              : 'the harness, deterministically (this family has no plan step)'}
        </dd>
        {plan.round > 0 && (
          // A round-1 plan is the Designer answering the gaps its own
          // Developers left, which is a different thing from its first
          // division and reads wrong without saying so.
          <><dt>Round</dt><dd>{plan.round} (re-planned against what the checks found)</dd></>
        )}
        <dt>Sets</dt><dd>{plan.work_sets.length}</dd>
        {Number(action.context.oversized_splits) > 0 && (
          // The one number that separates a planner scoping its own sets from
          // one the backstop is carrying.
          <>
            <dt>Cut by the harness</dt>
            <dd>{String(action.context.oversized_splits)} set(s) too large to answer</dd>
          </>
        )}
        {Number(action.context.duplicate_pairs) > 0 && (
          <><dt>Named twice</dt><dd>{String(action.context.duplicate_pairs)} pair(s), kept once</dd></>
        )}
        {Number(action.context.dropped_pairs) > 0 && (
          <><dt>Off target</dt><dd>{String(action.context.dropped_pairs)} pair(s) discarded</dd></>
        )}
      </dl>
      {plan.work_sets.map((set) => <WorkSetRow key={set.set_id} set={set} />)}
    </div>
  )
}

function WorkSetRow({ set }: { set: WorkSet }) {
  const payload = Object.entries(set.payload ?? {}).filter(([, value]) => value !== null && value !== '')
  return (
    <div className="hop" style={{ marginTop: 8 }}>
      <div className="hop-head small">
        <span className="mono">{set.set_id}</span>
        {/* The ordinal is not decoration: it is the first half of every id this
            set's Developer commits under, fixed before it runs. */}
        <span className="muted"> — set {set.ordinal}, {set.source}</span>
      </div>
      {set.objectives.length > 0 && (
        <div className="chips">
          {set.objectives.map((objective) => (
            <span key={objective} className="chip mono">{objective}</span>
          ))}
        </div>
      )}
      {set.pairs.length > 0 && (
        <div className="chips">
          {set.pairs.map((pair, index) => (
            <span key={index} className="chip mono">{pair.join(' × ')}</span>
          ))}
        </div>
      )}
      {payload.length > 0 && (
        <Collapsible title="What this Developer was handed">
          <JsonRoot value={set.payload} defaultOpenDepth={2} />
        </Collapsible>
      )}
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
