import { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Wrench } from 'lucide-react'
import { agentHue, agentShortName, phaseLabel } from '../lib/phaseTimeline'
import { OUTCOME_LABELS, openReasonLabel, violationLabel } from '../lib/violations'
import type { Finding } from '../api/types'

interface Props {
  findings: Finding[]
}

/**
 * What the run found wrong, and what became of it.
 *
 * The question that produced this tab: a violation appeared in the graph
 * inspector labelled "Bloom level consistent" with no indication of WHY, and
 * answering it meant opening the trajectory and reading check events by hand.
 * Nothing in the app had ever seen a violation's message — every view was
 * built from counters on the event stream.
 *
 * Grouped by OUTCOME rather than by type, because the first question about a
 * finished run is "what is still wrong", and the second is "did anything fix
 * it". Within a group, ordered as the run met them.
 */
export function ViolationGrid({ findings }: Props) {
  const [openKey, setOpenKey] = useState<string | null>(null)
  const groups = useMemo(() => {
    const open = findings.filter((f) => f.outcome === 'open')
    const fixed = findings.filter((f) => f.outcome !== 'open')
    return [
      { id: 'open', title: 'Still open', rows: open },
      { id: 'fixed', title: 'Repaired', rows: fixed },
    ].filter((g) => g.rows.length > 0)
  }, [findings])

  if (findings.length === 0) {
    return (
      <div className="empty">
        Every check the run ran came back clean, or the run has not reached its
        first check yet.
      </div>
    )
  }

  return (
    <div className="scroll">
      <div className="ctx-toolbar">
        <span className="muted small">
          {findings.length} distinct finding{findings.length === 1 ? '' : 's'} ·{' '}
          {findings.filter((f) => f.outcome === 'open').length} still open
        </span>
      </div>
      {groups.map((group) => (
        <div key={group.id} className="ctx-list">
          <div className="vg-group">{group.title}</div>
          {group.rows.map((finding) => (
            <ViolationRow
              key={finding.key}
              finding={finding}
              open={openKey === finding.key}
              onToggle={() => setOpenKey(openKey === finding.key ? null : finding.key)}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

function ViolationRow({ finding, open, onToggle }: {
  finding: Finding
  open: boolean
  onToggle: () => void
}) {
  const isOpen = finding.outcome === 'open'
  const hue = agentHue(finding.target_designer || 'WorkflowOrchestrator')
  return (
    <div className={`ctx-row${open ? ' open' : ''}`}>
      <button className="ctx-head" onClick={onToggle}>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {isOpen
          ? <AlertTriangle size={13} className="vg-open" />
          : <CheckCircle2 size={13} className="vg-fixed" />}
        <span className="ctx-title">
          {violationLabel(finding.type)}
          <span className="mono small muted"> {finding.node_id}</span>
        </span>
        <span className="muted small ctx-meta">
          {isOpen
            // The whole point of the ledger: a finding the model could not fix
            // and one we did not give another turn are different results, and
            // only the second is ours to change.
            ? openReasonLabel(finding.open_reason)
            : OUTCOME_LABELS[finding.outcome]}
        </span>
      </button>

      {open && (
        <div className="ctx-body">
          <div className="vg-facts">
            {finding.target_designer && (
              <span className="pt-pill" style={{ background: hue.bg, color: hue.fg }}>
                {agentShortName(finding.target_designer)}
              </span>
            )}
            <span className="muted small">
              first seen in {phaseLabel(finding.first_phase)} (round {finding.first_round})
              {finding.sightings > 1 && `, found again ${finding.sightings - 1}×`}
            </span>
            {finding.shown_to_agent > 0 && (
              <span className="muted small">
                · shown to the agent {finding.shown_to_agent}×
              </span>
            )}
            {finding.report_only && (
              // A policy fact about the HARNESS, not an outcome: these are
              // shown to the owning agent like any other violation, so
              // "report-only and repaired by the agent" is a real state.
              <span className="ctx-badge" title="the deterministic net is designed never to write this — only an agent can">
                agent-only
              </span>
            )}
          </div>

          {finding.messages.map((message, i) => (
            <p key={i} className="vg-message">{message}</p>
          ))}

          {finding.repair_hint && (
            <p className="vg-hint">
              <Wrench size={11} /> {finding.repair_hint}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
