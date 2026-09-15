import { useMemo, useState } from 'react'
import {
  ChevronDown, ChevronUp, Download, GitBranch, Layers, Loader2, ShieldCheck, Sparkles,
} from 'lucide-react'
import { api } from '../api/client'
import {
  agentHue, agentShortName, buildPhaseTimeline, phaseLabel,
  timelineAgents, writesSummary, type PhaseBlock,
} from '../lib/phaseTimeline'
import { foldChronological, type DeepRow } from '../lib/deepTimeline'
import type { DeepAction, Selection } from '../api/types'

interface Props {
  actions: DeepAction[]
  /** Null before the first run of this program. */
  runId: string | null
  runStarted: boolean
  runActive: boolean
  selection: Selection
  onSelect: (selection: Selection) => void
  /** The graph's `relation_coverage`, carrying each relation's canonical
   *  wording from `alignment.REGISTRY` — so a C/P relation is named in exactly
   *  one place for the whole app. */
  relations?: Record<string, { label?: string }>
}

/**
 * The run as a story: a vertical, phase-anchored timeline.
 *
 * Time flows down the rail; each ADDIE stage is one card summarised to its
 * beats (model turns → work sets dispatched → artifacts submitted →
 * self-check). The parallel-group rendering is retained for archived runs from
 * the concurrent pipeline; the executor is sequential today. The full
 * audit detail is behind each card's "N graph ops" chip (or all at once via
 * the Audit toggle) — demoted, never dropped.
 */
export function PhaseTimeline({
  actions, runId, runStarted, runActive, selection, onSelect, relations,
}: Props) {
  const blocks = useMemo(() => buildPhaseTimeline(actions), [actions])
  const agents = useMemo(() => timelineAgents(blocks), [blocks])
  const [agentFilter, setAgentFilter] = useState<string | null>(null)
  const [audit, setAudit] = useState(false)

  if (blocks.length === 0) {
    return <div className="empty">The run's activity appears here phase by phase.</div>
  }

  return (
    <div className="scroll">
      <div className="phase-timeline">
        <div className="pt-toolbar">
          <span className="muted small">Agents:</span>
          {agents.map((agent) => {
            const hue = agentHue(agent)
            const active = agentFilter === agent
            return (
              <button
                key={agent}
                className={`pt-chip${active ? ' active' : ''}`}
                style={{ background: hue.bg, color: hue.fg, borderColor: active ? hue.fg : 'transparent' }}
                onClick={() => setAgentFilter(active ? null : agent)}
                title={active ? 'Show all agents' : `Focus ${agent}`}
              >
                {agentShortName(agent)}
              </button>
            )
          })}
          <button
            className={`btn small pt-audit-toggle${audit ? ' active' : ''}`}
            onClick={() => setAudit((value) => !value)}
            title={audit
              ? 'Fold each phase back to its beats'
              : 'Expand every phase to the full deep action log — every read, write, edge and check, in recorded order'}
          >
            {/* Not "Audit": in this codebase that word is the residual
                ALIGNMENT audit of the finished design, which this same card
                already reports ("graph audit: N gaps"). Two meanings of it on
                one screen is exactly what the package's own naming rule
                forbids — and the label was also hiding what the expansion is,
                which is the deep trajectory this tab is built from. */}
            {audit ? 'Story' : 'Deep log'}
          </button>
          {runId && runStarted && (
            // Here rather than in the run header: what it exports is THIS view's
            // data, and an export control sitting next to Run/Cancel reads as a
            // run-level action that would carry the whole run with it.
            //
            // A link, not a fetch-and-blob: the server names the file in
            // Content-Disposition, and pulling the JSON into memory only to
            // re-serialize it here would drop that name and re-encode a file
            // that is already exactly what should land on disk.
            <a
              className="btn small icon-label"
              href={api.trajectoryExportUrl(runId)}
              download
              title={runActive
                ? 'Download what has been recorded so far (marked incomplete)'
                : 'Download this trajectory: the judge-visible streams and the full action log'}
            >
              <Download size={12} />
              {runActive ? 'Export so far' : 'Export'}
            </a>
          )}
        </div>

        <div className="pt-rail">
          {groupParallel(blocks).map((group) =>
            group.length === 1 ? (
              <Block
                key={group[0].id}
                block={group[0]}
                dimmed={isDimmed(group[0], agentFilter)}
                audit={audit}
                selection={selection}
                onSelect={onSelect}
                relations={relations}
              />
            ) : (
              // Same order they started in, not a 2-column layout: two agents
              // running at once still read top-to-bottom, just visibly boxed
              // together as one concurrent group.
              <div key={group[0].id} className="pt-parallel-group">
                <span className="pt-dot" style={{ background: 'var(--muted)' }} />
                <div className="pt-parallel-label muted small">
                  <GitBranch size={11} /> run concurrently
                </div>
                {group.map((block) => (
                  <Block
                    key={block.id}
                    block={block}
                    dimmed={isDimmed(block, agentFilter)}
                    audit={audit}
                    selection={selection}
                    onSelect={onSelect}
                    relations={relations}
                  />
                ))}
              </div>
            ),
          )}
        </div>
      </div>
    </div>
  )
}

function isDimmed(block: PhaseBlock, agentFilter: string | null): boolean {
  // Harness blocks (aggregate) stay visible under any filter: they are the
  // connective tissue the filtered agent's work runs through. A stage block
  // matches on any agent that acted in it, so filtering to a Developer keeps
  // the stage it worked inside.
  return agentFilter !== null && block.kind === 'generation'
    && !block.agents.includes(agentFilter)
}

/** Consecutive blocks sharing a parallel group id render side by side. */
function groupParallel(blocks: PhaseBlock[]): PhaseBlock[][] {
  const groups: PhaseBlock[][] = []
  for (const block of blocks) {
    const previous = groups[groups.length - 1]
    if (
      block.parallelGroup !== null &&
      previous &&
      previous[0].parallelGroup === block.parallelGroup
    ) {
      previous.push(block)
      continue
    }
    groups.push([block])
  }
  return groups
}

function Block({
  block, dimmed, audit, selection, onSelect, relations,
}: {
  block: PhaseBlock
  dimmed: boolean
  audit: boolean
  selection: Selection
  onSelect: (selection: Selection) => void
  relations?: Record<string, { label?: string }>
}) {
  return (
    <PhaseCard block={block} dimmed={dimmed} audit={audit} selection={selection}
               onSelect={onSelect} relations={relations} />
  )
}

function PhaseCard({
  block, dimmed, audit, selection, onSelect, relations,
}: {
  block: PhaseBlock
  dimmed: boolean
  audit: boolean
  selection: Selection
  onSelect: (selection: Selection) => void
  relations?: Record<string, { label?: string }>
}) {
  const [expanded, setExpanded] = useState(false)
  const open = audit || expanded
  const hue = agentHue(block.agent)
  const recoveryTotal = Object.values(block.recoveries).reduce((sum, n) => sum + n, 0)

  return (
    <div className={`pt-item${dimmed ? ' pt-dimmed' : ''}`}>
      <span className="pt-dot" style={{ background: hue.dot }} />
      <header className="pt-head">
        {block.kind === 'aggregate' && <Layers size={14} className="pt-head-icon" />}
        <span className="pt-title">{phaseLabel(block.phase)}</span>
        {block.agent && (
          <span className="pt-pill" style={{ background: hue.bg, color: hue.fg }}>
            {agentShortName(block.agent)}
          </span>
        )}
        {/* The Developers this stage dispatched to, named: the fan-out is the
            multi-agent claim at its second scale, and a card that showed only
            the Designer would hide it. */}
        {block.agents.slice(1).map((agent) => {
          const developerHue = agentHue(agent)
          return (
            <span
              key={agent}
              className="pt-pill"
              style={{ background: developerHue.bg, color: developerHue.fg, opacity: 0.75 }}
            >
              {agentShortName(agent)}
            </span>
          )
        })}
        <span className="pt-meta muted small">
          {block.durationMs !== null ? `${Math.round(block.durationMs / 1000)}s` : <Loader2 size={13} className="spin" />}
        </span>
      </header>

      {block.kind === 'aggregate' ? (
        <div className="pt-line">
          <span className={`pt-pill ${block.schemaErrors === 0 ? 'pt-ok' : 'pt-bad'}`}>
            {block.schemaErrors === 0
              ? 'schema valid'
              : `${block.schemaErrors ?? '?'} schema problem${block.schemaErrors === 1 ? '' : 's'}`}
          </span>
          {/* The residual whole-graph audit — the run's actual auditability
              claim — used to live only in metadata.audit, invisible here. */}
          {block.auditGapCount !== null && (
            <span className={`pt-pill ${block.auditGapCount === 0 ? 'pt-ok' : 'pt-gap'}`}>
              {block.auditGapCount === 0
                ? 'graph audit: no gaps'
                : `graph audit: ${block.auditGapCount} gap${block.auditGapCount === 1 ? '' : 's'} (${block.auditGappedRelations.join(', ')})`}
            </span>
          )}
        </div>
      ) : (
        <>
          <div className="pt-line">
            <Sparkles size={13} className="pt-line-icon" />
            <span>
              {/* One turn of the act->observe loop, not one generation: a stage
                  reads, submits, and is answered, so turns and artifacts are
                  different counts and both matter. */}
              {block.modelCalls} model turn{block.modelCalls === 1 ? '' : 's'}
              {block.workSets > 0 && (
                // Clickable, because "dispatch 4 work sets" is where the
                // question starts and the answer — what each Developer was
                // handed — is one artifact away. Every dev_plan action of the
                // block travels, so a stage that re-planned shows both rounds.
                <> · dispatch{' '}
                  <button
                    className="pt-inline"
                    onClick={() => onSelect({
                      kind: 'action',
                      id: `${block.id}-plan`,
                      actions: block.actions.filter((a) => a.action === 'dev_plan'),
                    })}
                    title="What each Developer was asked for"
                  >
                    {block.workSets} work set{block.workSets === 1 ? '' : 's'}
                  </button>
                </>
              )}
              {Object.keys(block.writes).length > 0 && (
                <> → submit <strong>{writesSummary(block.writes)}</strong></>
              )}
              {block.edgesDrawn > 0 && <> · draw {block.edgesDrawn} edges</>}
            </span>
          </div>
          {block.routedViolations > 0 && (
            <div className="pt-line">
              <GitBranch size={13} className="pt-line-icon" />
              <span>
                routed <strong>{block.routedViolations}</strong> residual violation
                {block.routedViolations === 1 ? '' : 's'} here
                {block.routedViolationTypes.length > 0 && (
                  <span className="muted"> ({[...new Set(block.routedViolationTypes)].join(', ')})</span>
                )}
              </span>
            </div>
          )}
          {(block.checkRounds.length > 0 || recoveryTotal > 0) && (
            <div className="pt-line">
              <ShieldCheck size={13} className="pt-line-icon" />
              <span>
                {block.checkRounds.length > 0 && (
                  <>
                    self-check:{' '}
                    {block.checkRounds.map((count, i) => (
                      <span key={i}>
                        {i > 0 && ' → '}
                        <span className={`mono ${count === 0 ? 'pt-good' : 'pt-warn'}`}>{count}</span>
                      </span>
                    ))}
                    {block.repairs > 0 && (
                      <span className="muted"> ({block.repairs} repair{block.repairs === 1 ? '' : 's'})</span>
                    )}
                  </>
                )}
                {recoveryTotal > 0 && (
                  <span className="pt-recovery">
                    {Object.entries(block.recoveries)
                      .map(([action, count]) => `${count}× ${action}`)
                      .join(', ')}
                  </span>
                )}
              </span>
            </div>
          )}
        </>
      )}

      <AuditChip block={block} open={open} onToggle={() => setExpanded((value) => !value)} />
      {open && <AuditRows block={block} selection={selection} onSelect={onSelect} relations={relations} />}
    </div>
  )
}

function AuditChip({
  block, open, onToggle,
}: {
  block: PhaseBlock
  open: boolean
  onToggle: () => void
}) {
  const parts: string[] = []
  if (block.graphOps > 0) parts.push(`${block.graphOps} graph ops`)
  if (block.edgesReverified > 0) parts.push(`${block.edgesReverified} re-verified`)
  if (parts.length === 0 && block.actions.length === 0) return null

  return (
    <button className="pt-audit-chip" onClick={onToggle}>
      {parts.join(' · ') || `${block.actions.length} actions`}
      {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
    </button>
  )
}

/** Full audit detail for one phase, strictly in recorded order: only an
 *  unbroken run of the same bulk work (reads, writes) collapses into one row,
 *  which stays at its chronological position — so check → repair → check
 *  reads exactly as it happened. Clicking a row opens it in the inspector. */
function AuditRows({
  block, selection, onSelect, relations,
}: {
  block: PhaseBlock
  selection: Selection
  onSelect: (selection: Selection) => void
  relations?: Record<string, { label?: string }>
}) {
  const rows = useMemo(() => foldChronological(block.actions, relations), [block.actions, relations])
  const selectedId = selection.kind === 'action' ? selection.id : null

  return (
    <div className="pt-audit-rows">
      {rows.map((row) => (
        <AuditRow
          key={`${block.id}-${row.id}`}
          row={row}
          selected={selectedId === `${block.id}-${row.id}`}
          onSelect={() => onSelect({ kind: 'action', id: `${block.id}-${row.id}`, actions: row.actions })}
        />
      ))}
    </div>
  )
}

function AuditRow({ row, selected, onSelect }: { row: DeepRow; selected: boolean; onSelect: () => void }) {
  return (
    <button className={`pt-audit-row${row.tone ? ' ' + row.tone : ''}${selected ? ' selected' : ''}`} onClick={onSelect}>
      <span className="pt-audit-title">{row.title}</span>
      <span className="mono pt-audit-action">{row.action}</span>
      <span className="muted small pt-audit-detail">{row.detail}</span>
    </button>
  )
}
