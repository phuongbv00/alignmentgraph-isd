"""Every ceiling the executor spends against, in one place.

What lives here is one kind of number: **how many times** a loop may go round
before the harness stops it — turns, retries, refunds, rounds. They were spread
over five modules (``loop``, ``react``, ``fanout``, ``replan``, ``outputs``),
which is the wrong shape for them for a reason that is not tidiness: several of
them are COUPLED ACROSS the decomposition axis, and a ceiling that ends up
different on one side of that axis sits INSIDE the treatment. ``react.MAX_TURNS``
is derived from ``STAGE_MAX_TURNS`` precisely so the two arms cannot drift
apart; ``THINKING_ALLOWANCE`` and ``REPEAT_ALLOWANCE`` are mirrored in both
loops for the same reason. Numbers that must move together are easier to keep
together when they are next to each other.

What deliberately does NOT live here: the **how big** caps — ``HISTORY_CHAR_BUDGET``
and ``TRIM_LOW_WATER`` in ``loop``, ``NODE_CHAR_CAP`` / ``READ_CHAR_BUDGET`` in
``tools``, ``ASSIGNMENT_CHAR_CAP`` in ``fanout``, ``SET_OUTPUT_BUDGET`` in
``dev_plans``, ``MAX_INPUT_CHARS`` / ``MAX_SUMMARY_CHARS`` in
``compaction``. Those are properties of the renderer or the trimmer that enforces
them, they are read at the point of enforcement and nowhere else, and reading
one apart from the code that spends it tells you nothing.

Derived values also stay at their derivation site, because a derived value is
not a knob: ``react.MAX_TURNS`` is composed here from ``STAGE_MAX_TURNS`` and
``SINGLE_ARM_TURN_FACTOR`` but multiplied by ``len(STEPS)`` there, where the
stage list is.

A LEAF on purpose: nothing in this module imports anything, so any module can
read it without a cycle.
"""
from __future__ import annotations

#: Turns one STAGE may spend. The single arm's whole-run ceiling is derived
#: from this (``react.MAX_TURNS``) so the two cannot drift apart: a per-stage
#: budget raised here while the other stayed on a hard-coded 8 would quietly
#: put a different ceiling on each side of the decomposition axis.
#:
#: Raised 8 -> 12 (2026-09-02). MEASURED (run f42dceff): all five
#: ``agentic_gave_up`` events read "turn budget exhausted", and a stage that
#: gives up is REGENERATED — the implementation stage spent 16 calls as 8 x 2
#: attempts. Twelve turns once is cheaper than eight twice whenever it converts
#: a give-up into a completion, so the raise can pay for itself.
#:
#: It does not fix what is actually eating the turns: 62% of that run's calls
#: were reads or repeats of material the prompt already carried. A ceiling
#: raised over that waste buys more of it.
#:
#: Raised 12 -> 24 (2026-09-06). MEASURED over runs single_20260903_224852,
#: single_20260904_014449 and single_20260904_020259: 24 of 27
#: ``agentic_gave_up`` events read "turn budget exhausted", and the single arm
#: hit its whole-run ceiling outright -- ``via_budget_exhaustion`` true at 144
#: -- while multi never reached its own. A ceiling that binds ASYMMETRICALLY
#: sits INSIDE the decomposition treatment, which is the one thing
#: ``test_the_agentic_arms_are_two_shapes_not_two_settings`` exists to rule
#: out, so an outcome difference measured under it could not be attributed to
#: the axis at all.
#:
#: Provisional, and doubling rather than fitting is the point: this lifts the
#: safety stop clear of the work instead of asserting how many turns the work
#: needs. Those runs predate the 2026-09-06 read-cost cut (``render_listing``)
#: and the stage brief going back into the turn, both of which take turns off
#: the same stages, so the number to settle on comes from re-measuring
#: ``turns_used`` on a tune slice -- with the note above still standing, since
#: a ceiling raised over waste buys more waste.
STAGE_MAX_TURNS = 24

#: How many stage-budgets the single arm gets for the whole brief. It walks the
#: same six stages in one conversation, so the ceiling is per-stage x stages x
#: this. The factor is slack, not a second policy: the arm plans its own order
#: and may revisit a stage, which a fixed walk cannot.
SINGLE_ARM_TURN_FACTOR = 2

#: Turn budget for ONE Developer call. Smaller than a stage's, because a
#: Developer's job is smaller: its assignment is in its prompt, so a read or two
#: and a submit is the whole shape.
#:
#: Raised 4 -> 6 (2026-09-02). The number it was set to was BELOW the measured
#: need: 5.4 turns per material set, of which one was the submit. A cap under
#: what the work actually takes does not economise, it manufactures give-ups —
#: and a Developer that gives up is regenerated, so the set costs 4 turns and
#: then 4 more. Observed shape on run f42dceff was read -> repeated read ->
#: submit, which leaves a cap of 4 with exactly one spare turn and a set that
#: needs a second genuine read with none.
#:
#: Raised 6 -> 12 with the stage ceiling (2026-09-06), and for the same reason
#: on this loop's own evidence: 5 of the 24 "turn budget exhausted" give-ups in
#: those three runs were MaterialDeveloperAgent, one per material work unit
#: (MU-MOD-01-02, -03, -04 twice, -05). A Developer that gives up is
#: regenerated, so each of those cost the unit twice over. Kept at half the
#: stage budget: the ratio is the statement that a Developer's job is smaller,
#: and nothing measured says that stopped being true.
DEVELOPER_MAX_TURNS = 12

#: Rejected submits allowed per ARTIFACT before it is dropped with a note and
#: the stage keeps going. Raised from 2 when ``check_artifact`` was dropped:
#: that tool gave the model unlimited validation attempts at the price of
#: re-writing the whole artifact each time. A rejected submit returns the
#: identical errors and costs no extra writing, so the retry allowance belongs
#: here, where it is explicit and equal across arms.
SUBMIT_BUDGET = 3

#: Accepted submits allowed beyond one per artifact, for an artifact that comes
#: back hollow and is sent again. Every stage has several artifacts now (one
#: submit tool each), so this is on every stage's path; a work set has none and
#: returns on its first accepted submit.
PART_SUBMIT_SLACK = 3

#: How many times one stage may be submitted before the SINGLE arm's loop stops
#: accepting it. Generous — additive submits are the point — but finite. Counts
#: ACCEPTED submits and REJECTED ones together: they cost the same turn, and a
#: stage that cannot pass its validator is exactly the case the cap exists for.
#: Measured (run single_20260901_205901): counting only accepted submits left
#: `assessment` at 1 while it was rejected 61 more times on one unparseable
#: argument — the arm burned all 96 turns, reached 3 of 6 stages, and scored
#: 0.0 on Analysis and Implementation.
#:
#: Deliberately NOT equal to ``SUBMIT_BUDGET``: that one is per artifact and
#: this one is per stage, and both are non-terminal, so the arms are close but
#: not identical here — stated rather than hidden.
SUBMIT_CAP = 8

#: How many repeated calls are refunded rather than charged a turn.
REPEAT_ALLOWANCE = 3

#: How many reasoning-only replies are refunded rather than charged a turn.
#: Same shape and same argument as REPEAT_ALLOWANCE: the turn produced no
#: observation and no artifact, so charging it spends the stage's budget on a
#: serving posture. Bounded for the same reason too — a backend that only ever
#: returns reasoning must still reach the ceiling rather than loop. Mirrored in
#: `ReactLoop`: a refund is a harness accounting rule, so one that existed on a
#: single side of the decomposition axis would be a ceiling difference sitting
#: inside the treatment.
THINKING_ALLOWANCE = 3

#: Default turns a STAGE loop may spend fixing its own violations. Passed in by
#: ``run.py``; a Developer loop gets 0.
#:
#: Repair used to happen entirely outside the loop: the checks ran after it
#: returned, and a generative fix was composed as a separate persona-free
#: prompt the agent never saw. That worked, but it meant the agent could not
#: learn from a violation, and it forced nine violation types to be
#: REPORT_ONLY — because a DETERMINISTIC fix for them would have been the
#: harness inventing instructional content, which is the one thing a repair
#: must never do. An agent writing that content is not inventing it; it is the
#: agent doing its job with feedback.
#:
#: Bounded tightly. Each round costs a whole stage context (measured: 5-15x a
#: targeted repair prompt), and an agent that cannot fix a violation in three
#: rounds is not going to.
REPAIR_TURNS = 3

#: How many violations one repair request names. A list longer than this is a
#: wall of text a small model answers by rewriting everything.
REPAIR_REQUEST_CAP = 6

#: Turns the Designer gets to answer a replan request with a plan. Its whole
#: job is one artifact: the gaps are in the request in front of it and there is
#: one ``submit_dev_plan`` bound, so a read or two and a submit is the shape.
#:
#: WIRED 2026-09-06 (declared 2026-09-03 as 4, never passed to anything — the
#: replan loop was built with no ``max_turns`` and silently took the whole
#: stage ceiling). Set to 8 rather than the declared 4 for a floor that is not
#: a matter of taste: a round has to survive ``SUBMIT_BUDGET`` rejections and
#: still land the accepted submit, so anything at or under 4 can lose the round
#: to rejections alone and produce nothing — which is exactly how run 2b9e911a
#: lost a replan work set, three "arrived as text" rejections on one malformed
#: array. Floor is therefore SUBMIT_BUDGET + 1 submit + a read; 8 is that with
#: one spare, and half the ratio the stage ceiling carries.
REPLAN_TURNS = 8

#: Replan rounds per family, per run. A gap that survives a Designer re-plan
#: and a fresh Developer call is a gap the model cannot close, and asking again
#: is how a stage turns into a hang.
REPLAN_ROUNDS = 1

#: Rounds of check -> route -> repair -> re-check, both within a stage and in
#: the cross-family reconciliation pass after the last one. Bounded because
#: route/repair/recheck is no longer bounded by the stage order, and unbounded
#: on an SLM it is a hang.
SELF_VALIDATION_BUDGET = 2
