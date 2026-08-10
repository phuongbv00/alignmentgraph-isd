import { useMemo, useState } from 'react'
import {
  ArrowRightLeft, Bot, CircleAlert, ClipboardCheck, Eye, FilePenLine, Link2,
  Search, ShieldCheck, Sparkles, Wrench,
} from 'lucide-react'
import { groupDeepActions, phaseLabel, type AgentGroup, type DeepRow, type WorkKind } from '../lib/deepTimeline'
import type { DeepAction, Selection } from '../api/types'

interface Props {
  actions: DeepAction[]
  selection: Selection
  onSelect: (selection: Selection) => void
}

const ICONS: Record<WorkKind, typeof Eye> = {
  read: Search,
  walk: ArrowRightLeft,
  write: FilePenLine,
  link: Link2,
  model: Sparkles,
  step: Bot,
  verify: ShieldCheck,
  repair: Wrench,
  validate: ClipboardCheck,
  retrieval: Eye,
  error: CircleAlert,
  phase: Bot,
  other: Bot,
}

const TALLY_LABEL: Partial<Record<WorkKind, string>> = {
  read: 'reads',
  walk: 'walks',
  write: 'nodes written',
  link: 'edges drawn',
  model: 'model calls',
  verify: 'checks',
  repair: 'repairs',
}

/**
 * What each agent did, in order.
 *
 * The point of the deep trajectory is that an agent is not just "a model call":
 * it reads the graph its predecessors built, writes nodes, and draws the
 * alignment edges that are the contribution. This view is organised around
 * that, with the model call as one action among several rather than the only
 * thing on screen.
 */
export function DeepTimeline({ actions, selection, onSelect }: Props) {
  const groups = useMemo(() => groupDeepActions(actions), [actions])

  if (groups.length === 0) {
    return (
      <div className="empty">
        Nothing yet. Start a run and each agent's work appears here as it happens —
        what it read from the graph, what it wrote, and which alignment edges it drew.
      </div>
    )
  }

  return (
    <div className="scroll">
      <div className="deep-timeline">
        {groups.map((group) => (
          <AgentBlock key={group.id} group={group} selection={selection} onSelect={onSelect} />
        ))}
      </div>
    </div>
  )
}

function AgentBlock({
  group, selection, onSelect,
}: {
  group: AgentGroup
  selection: Selection
  onSelect: (selection: Selection) => void
}) {
  const selectedId = selection.kind === 'action' ? selection.id : null

  return (
    <section className="agent-block">
      <header className="agent-head">
        <span className="agent-name">{group.actor}</span>
        <span className="agent-phase muted small">{phaseLabel(group.phase)}</span>
        <span className="agent-tally">
          {(Object.entries(group.tally) as [WorkKind, number][])
            .filter(([kind]) => TALLY_LABEL[kind])
            .sort((a, b) => b[1] - a[1])
            .map(([kind, count]) => (
              <span key={kind} className="chip">{count} {TALLY_LABEL[kind]}</span>
            ))}
        </span>
      </header>

      {group.rows.map((row) => (
        <WorkRow
          key={row.id}
          row={row}
          selected={selectedId === row.id}
          onSelect={() => onSelect({ kind: 'action', id: row.id, actions: row.actions })}
        />
      ))}
    </section>
  )
}

function WorkRow({ row, selected, onSelect }: { row: DeepRow; selected: boolean; onSelect: () => void }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = ICONS[row.kind]
  const collapsible = row.count > 1

  return (
    <>
      <div className={`work-row ${row.kind}${row.tone ? ' ' + row.tone : ''}${selected ? ' selected' : ''}`}>
        <button className="work-main" onClick={onSelect}>
          <Icon size={13} className="work-icon" />
          <span className="work-title">{row.title}</span>
          <span className="work-detail muted small">{row.detail}</span>
        </button>
        {collapsible && (
          <button
            className="btn small work-expand"
            onClick={() => setExpanded((v) => !v)}
            title={expanded ? 'Collapse' : `Show all ${row.count}`}
          >
            {expanded ? 'less' : `${row.count}`}
          </button>
        )}
      </div>

      {expanded && (
        <div className="work-children">
          {row.actions.map((action) => (
            <div key={action.seq} className="work-child small mono">
              {describe(action)}
            </div>
          ))}
        </div>
      )}
    </>
  )
}

/** One line for a single action, when a collapsed run is opened up. */
function describe(action: DeepAction): string {
  switch (action.kind) {
    case 'node_read':
      return `${action.query}(${action.node_type ?? action.node_id ?? ''}) → ${action.result_count}`
    case 'edge_read':
      return `${action.query}(${action.edge_type}, ${action.relation_id}) → ${action.result_count}`
    case 'edge_walk':
      return `${action.query}(${action.node_id}) via ${(action.rel_path ?? []).join(' → ')} → ${action.result_count}`
    case 'node_write':
      return `${action.op} ${action.node_id} [${(action.fields ?? []).join(', ')}]`
    case 'edge_write':
      return `${action.op} ${action.edge_type}: ${action.source} → ${action.target}` +
        (action.evidence ? `  (evidence: ${action.evidence})` : '')
    default:
      return `${action.kind} ${JSON.stringify(
        Object.fromEntries(
          Object.entries(action).filter(
            ([k]) => !['seq', 'kind', 'actor', 'phase', 'elapsed_ms', 'timestamp'].includes(k),
          ),
        ),
      ).slice(0, 200)}`
  }
}
