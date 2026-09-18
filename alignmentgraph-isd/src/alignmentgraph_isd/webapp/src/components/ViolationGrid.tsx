import { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Download, Wrench } from 'lucide-react'
import { agentHue, agentShortName, phaseLabel } from '../lib/phaseTimeline'
import { OUTCOME_LABELS, openReasonLabel, violationLabel } from '../lib/violations'
import { api } from '../api/client'
import type { Finding } from '../api/types'

interface Props {
  findings: Finding[]
  runId: string | null
  /** Whether the run is still going. The ledger streams as it fills, so this
   *  tab is provisional while that is true: a row's outcome can still change,
   *  and the export says so in its filename. Only the WORDING depends on it —
   *  whether a finding has been explained yet is read off the finding itself
   *  (`openReasonLabel`), which stays right for a cancelled run too. */
  runActive: boolean
  /** The graph's `relation_coverage`, which carries each relation's canonical
   *  wording from `alignment.REGISTRY`. Passed in rather than looked up here,
   *  so a C/P relation is named in exactly one place for the whole app. */
  relations?: Record<string, { label?: string }>
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
 *
 * LIVE: the ledger is published whenever a finding is written, so rows appear
 * while the run is still going and move between the groups as the repair net
 * closes them. That is worth watching, but it means every group here is a
 * snapshot until the run settles — hence the "so far" wording below.
 */
export function ViolationGrid({ findings, runId, runActive, relations }: Props) {
  const [openKey, setOpenKey] = useState<string | null>(null)
  const groups = useMemo(() => {
    const open = findings.filter((f) => f.outcome === 'open')
    const fixed = findings.filter((f) => f.outcome !== 'open')
    return [
      { id: 'open', title: runActive ? 'Open so far' : 'Still open', rows: open },
      { id: 'fixed', title: 'Repaired', rows: fixed },
    ].filter((g) => g.rows.length > 0)
  }, [findings, runActive])

  if (findings.length === 0) {
    // Three different nothings, and only the last is a result: no run to speak
    // of, a run whose checks have not caught up yet, and a run that genuinely
    // found nothing wrong — which is what the design is aiming at.
    return (
      <div className="empty">
        {!runId
          ? 'No run selected yet.'
          : runActive
            ? 'Nothing found yet — the first check has not run, or everything it looked at came back clean.'
            : 'Every check the run ran came back clean.'}
      </div>
    )
  }

  return (
    <div className="scroll">
      <div className="ctx-toolbar">
        <span className="muted small">
          {findings.length} distinct finding{findings.length === 1 ? '' : 's'}
          {runActive ? ' so far' : ''} ·{' '}
          {findings.filter((f) => f.outcome === 'open').length} still open
        </span>
        {runId && (
          // A link, not a fetch-and-blob: the server names the file in
          // Content-Disposition, and pulling the CSV into memory only to hand
          // it back to the browser would drop that name.
          <a
            className="btn small icon-label"
            href={api.violationsExportUrl(runId)}
            download
            title={runActive
              ? 'Download the findings so far as CSV (marked partial)'
              : 'Download every finding as CSV — one row per finding, with its outcome, why it is still open, and who owns it'}
          >
            <Download size={12} />
            {runActive ? 'Export so far' : 'Export'}
          </a>
        )}
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
              relations={relations}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

function ViolationRow({ finding, open, onToggle, relations }: {
  finding: Finding
  open: boolean
  onToggle: () => void
  relations?: Record<string, { label?: string }>
}) {
  const isOpen = finding.outcome === 'open'
  const hue = agentHue(finding.target_designer || 'Orchestrator')
  return (
    <div className={`ctx-row${open ? ' open' : ''}`}>
      <button className="ctx-head" onClick={onToggle}>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {isOpen
          ? <AlertTriangle size={13} className="vg-open" />
          : <CheckCircle2 size={13} className="vg-fixed" />}
        <span className="ctx-title">
          {violationLabel(finding.type, relations)}
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
