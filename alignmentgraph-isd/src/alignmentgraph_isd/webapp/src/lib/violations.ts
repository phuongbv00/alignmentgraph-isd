/** What a violation type is called, in words.
 *
 *  The FIRST such table in the repo. Until now the app showed raw snake_case
 *  straight from the checks — `bloom_mismatch_activity(2)` in the timeline —
 *  and the one place that did use words, the objective inspector's
 *  "Bloom level consistent" flag, was a hardcoded JSX literal on a boolean
 *  that had already unioned two different rules together. So the label a
 *  reader saw could not be traced to the check that produced it.
 *
 *  The C and P relation types take their wording from `alignment.REGISTRY`,
 *  which is where the canonical phrasing already lives; the rest are named
 *  after what the check asserts, not after what it forbids, so a clean design
 *  reads as a list of properties that hold.
 */
const LABELS: Record<string, string> = {
  // Core alignment relations (the construct-validity backbone)
  C1: 'objective derived from the course goal',
  C2: 'objective assessed by an assessment item',
  C3: 'objective practiced by an activity',
  C4: 'activity prepares for its assessment',
  C5: 'activity supported by content',
  // Secondary provenance relations
  P1: 'objective traceable to a gap or topic',
  P2: 'objective informed by the learner profile',
  P3: 'assessment item realises the plan',
  P4: 'activity realises the instructional strategy',
  P5: 'material traceable to a module',
  P6: 'media selection realised by a material',
  P7: 'module covers a task topic',
  P8: 'media selection respects a constraint',
  P9: 'improvement addresses a gap',
  P10: 'activity scheduled by a session guide',
  P11: 'material provisioned by a session guide',
  // Within-artifact quality checks
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
  orphan_content: 'content traces to instructional purpose',
  feasibility: 'plan fits the stated constraints',
  actionability: 'implementation plan is concrete enough to run',
}

export function violationLabel(type: string): string {
  return LABELS[type] ?? type
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

export function openReasonLabel(reason: string): string {
  return OPEN_REASONS[reason] ?? reason
}

export const OUTCOME_LABELS: Record<string, string> = {
  open: 'Still open',
  repaired_by_harness: 'Repaired by the harness',
  repaired_by_agent: 'Repaired by the agent',
}
