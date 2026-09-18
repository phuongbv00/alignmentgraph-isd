/** What a violation type is called, in words.
 *
 *  Until this existed the app showed raw snake_case straight from the checks —
 *  `bloom_mismatch_activity(2)` in the timeline — so the label a reader saw
 *  could not be traced to the check that produced it.
 *
 *  This table names CHECKS, and only checks. A relation (C1-C4, P1-P14) is
 *  named by `alignment.REGISTRY`, which travels in the graph payload as
 *  `relation_coverage[id].label` — so `violationLabel` is given that map and
 *  reads the wording from it.
 *
 *  It used to hold all sixteen relations too, under a comment claiming they
 *  took their wording from the registry. None of them did: every one was a
 *  paraphrase and most reversed the direction — C1 "objective derived from the
 *  course goal" for `decomposes_to`, P10 "activity scheduled by a session
 *  guide" for `delivers`, P5 "material traceable to a module" for `covers`.
 *  A second vocabulary for the thing this system is about is exactly what a
 *  single registry is for.
 */
const LABELS: Record<string, string> = {
  // Within-artifact quality checks, named after what the check ASSERTS rather
  // than what it forbids, so a clean design reads as properties that hold.
  bloom: "objective's Bloom verb and level agree",
  bloom_mismatch_assessment: 'objective assessed at its own Bloom level',
  bloom_mismatch_activity: 'objective practiced at its own Bloom level',
  measurability: 'objective states a success criterion',
  plan_coverage: 'every promised assessment pair is realised',
  item_completeness: 'item can be administered as written',
  evaluation_quality: 'evaluation plan names concrete methods',
  activity_engagement: 'higher-order objective practiced actively',
  rubric_consistency: 'rubric criterion is observable',
  evidence_alignment: 'criterion asks for evidence its item can give',
  // Recorded by runs from before the module became the course's structural
  // unit; a material with no module is reported as P5 coverage since.
  orphan_content: 'content traces to instructional purpose',
  time_budget: 'activities fit the time the course has',
  blueprint_consistency: 'assessment blueprint agrees with its coverage targets',
  instrument_alignment: 'item belongs to an instrument of the plan',
  feasibility: 'plan fits the stated constraints',
  actionability: 'implementation plan is concrete enough to run',
}

/** `relations` is the payload's `relation_coverage`, whose entries carry the
 *  registry's own `label`. Without it a relation id falls through as itself —
 *  "C4" reads as nothing, but it is at least not a word this system does not
 *  use. */
export function violationLabel(
  type: string,
  relations?: Record<string, { label?: string }>,
): string {
  return LABELS[type] ?? relations?.[type]?.label ?? type
}

/** Why a finding is still open. Four different facts that "open" alone hid —
 *  and the line between a result about the MODEL and a parameter we chose. */
const OPEN_REASONS: Record<string, string> = {
  converged: 'tried, could not be fixed',
  budget: 'ran out of repair budget',
  unowned: 'no agent owns this check',
  unseen: 'never shown to an agent',
  unexplained: 'still open, reason not recorded',
}

/** A finding with no reason recorded has not been SETTLED yet.
 *
 *  `Memory.settle` (core/memory.py) stamps `unexplained` on everything still
 *  open, so once a run has finished `outcome === 'open'` implies a non-empty
 *  `open_reason`. Blank therefore means exactly one thing: the ledger is still
 *  being written — the tab is live now, and a cancelled run keeps its partial
 *  ledger forever without ever reaching settle.
 *
 *  Handled here rather than by passing the run's live/finished state down to
 *  the row, because the fact is a property of the FINDING, and a cancelled run
 *  is not "active" yet still has unsettled rows. */
export function openReasonLabel(reason: string): string {
  if (!reason) return 'still being worked on'
  return OPEN_REASONS[reason] ?? reason
}

export const OUTCOME_LABELS: Record<string, string> = {
  open: 'Still open',
  repaired_by_harness: 'Repaired by the harness',
  repaired_by_agent: 'Repaired by the agent',
}
