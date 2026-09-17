"""Every ceiling the executor spends against, in one place.

What lives here is one kind of number: **how many times** a loop may go round
before the harness stops it — turns, retries, refunds, rounds.

They belong together because several of them are COUPLED ACROSS the
decomposition axis, and a ceiling that ends up different on one side of that
axis sits INSIDE the treatment. ``react.MAX_TURNS`` is derived from
``STAGE_MAX_TURNS`` precisely so the two arms cannot drift apart;
``REPEAT_ALLOWANCE`` and ``ERROR_ALLOWANCE`` are mirrored in both loops for
the same reason. Numbers that must move together are
easier to keep together when they are next to each other.

What deliberately does NOT live here: the **how big** caps —
``HISTORY_CHAR_BUDGET`` and ``TRIM_LOW_WATER`` in ``loop``, ``NODE_CHAR_CAP`` /
``READ_CHAR_BUDGET`` in ``tools``, ``ASSIGNMENT_CHAR_CAP`` in ``fanout``,
``SET_OUTPUT_BUDGET`` in ``dev_plans``, ``MAX_INPUT_CHARS`` /
``MAX_SUMMARY_CHARS`` in ``compaction``. Those are properties of the renderer or
the trimmer that enforces them, they are read at the point of enforcement and
nowhere else, and reading one apart from the code that spends it tells you
nothing.

Derived values also stay at their derivation site, because a derived value is
not a knob: ``react.MAX_TURNS`` is composed from ``STAGE_MAX_TURNS`` and
``SINGLE_ARM_TURN_FACTOR`` here but multiplied by ``len(STEPS)`` there, where
the stage list is.

A LEAF on purpose: nothing in this module imports anything, so any module can
read it without a cycle.
"""
from __future__ import annotations

#: Turns one STAGE may spend. The single arm's whole-run ceiling derives from
#: this (``react.MAX_TURNS``) so the two arms cannot carry different ceilings:
#: one that binds asymmetrically sits inside the decomposition treatment, which
#: is what ``test_the_agentic_arms_are_two_shapes_not_two_settings`` exists to
#: rule out — under it, an outcome difference could not be attributed to the
#: axis at all.
#:
#: Set to lift the safety stop clear of the work, not to fit it: a stage that
#: COMPLETES takes a median of 7 turns and never more than 13 (runs 53042a0d,
#: 2559b22d). PROVISIONAL — re-measure ``turns_used`` on a tune slice before the
#: final runs. Raising it over waste only buys more waste, so the ceiling is the
#: wrong answer to a stage that spends its turns on refused reads; the refunds
#: below are the right one.
STAGE_MAX_TURNS = 24

#: How many stage-budgets the single arm gets for the whole brief. It walks the
#: same six stages in one conversation, so the ceiling is per-stage x stages x
#: this. The factor is slack, not a second policy: the arm plans its own order
#: and may revisit a stage, which a fixed walk cannot.
SINGLE_ARM_TURN_FACTOR = 2

#: Turn budget for ONE Developer call. Smaller than a stage's, because a
#: Developer's job is smaller: its assignment is in its prompt, so a read or two
#: and a submit is the whole shape. Held at HALF the stage budget — the ratio is
#: the statement that the job is smaller, and a cap set under what the work
#: takes does not economise, it manufactures give-ups, and a Developer that
#: gives up is regenerated at full price.
DEVELOPER_MAX_TURNS = 12

#: Rejected submits allowed per ARTIFACT before it is dropped with a note and
#: the stage keeps going. A rejected submit returns the identical deterministic
#: errors and costs no extra writing, so the retry allowance belongs here, where
#: it is explicit and equal across arms.
SUBMIT_BUDGET = 3

#: Accepted submits allowed beyond one per artifact, for an artifact that comes
#: back hollow and is sent again. Every stage has several artifacts (one submit
#: tool each), so this is on every stage's path; a work set has none and returns
#: on its first accepted submit.
PART_SUBMIT_SLACK = 3

#: How many times one stage may be submitted before the SINGLE arm's loop stops
#: accepting it. Generous — additive submits are the point — but finite.
#:
#: Counts ACCEPTED and REJECTED submits together: they cost the same turn, and a
#: stage that cannot pass its validator is exactly the case the cap exists for.
#: Counting only the accepted ones lets a stage sit at 1 while it is rejected 61
#: more times on a single unparseable argument, burning every turn the arm has
#: (run single_20260901_205901: 3 of 6 stages reached, 0.0 on Analysis and
#: Implementation).
#:
#: Deliberately NOT equal to ``SUBMIT_BUDGET``: that one is per artifact and
#: this one is per stage, and both are non-terminal, so the arms are close but
#: not identical here — stated rather than hidden.
SUBMIT_CAP = 8

# The two refunds below are one family. A turn that produced no observation and
# no artifact — a repeat, or a call that came back ERROR — spends the stage's
# budget on the model's confusion rather than on the design, so it is refunded
# instead of charged. Each is BOUNDED all the same, so a model that only ever
# repeats or errors still reaches the ceiling rather than looping forever. Both
# are mirrored in ``ReactLoop``: a refund is a harness accounting rule, and one
# that existed on a single side of the decomposition axis would be a ceiling
# difference sitting inside the treatment.
#
# They are what a stage cut short actually needs. Measured over runs 53042a0d
# and 2559b22d, 63 of 476 tool results were ERROR and 84 more were repeat
# refusals: 31% of every turn taken produced no observation at all, and the
# stages that hit the ceiling had already submitted their artifacts and were
# looping on refused calls.

#: Repeated calls refunded rather than charged a turn.
REPEAT_ALLOWANCE = 3

#: Tool calls that came back ERROR, refunded rather than charged a turn.
ERROR_ALLOWANCE = 3

#: Default turns a STAGE loop may spend fixing its own violations. Passed in by
#: ``runner.py``; a Developer loop gets 0.
#:
#: Bounded tightly: each round costs a whole stage context (5-15x a targeted
#: repair prompt), and an agent that cannot fix a violation in three rounds is
#: not going to.
REPAIR_TURNS = 3

#: How many violations one repair request names. A list longer than this is a
#: wall of text a small model answers by rewriting everything.
REPAIR_REQUEST_CAP = 6

#: Turns the Designer gets to answer a replan request with a plan. Its whole job
#: is one artifact: the gaps are in the request in front of it and there is one
#: ``submit_dev_plan`` bound, so a read or two and a submit is the shape.
#:
#: The FLOOR is not a matter of taste — a round has to survive
#: ``SUBMIT_BUDGET`` rejections and still land the accepted submit, so anything
#: at or under 4 can lose the round to rejections alone and produce nothing (run
#: 2b9e911a lost a replan work set to three "arrived as text" rejections on one
#: malformed array). Floor is SUBMIT_BUDGET + 1 submit + a read; this is that
#: with one spare, and half the ratio the stage ceiling carries.
REPLAN_TURNS = 8

#: Replan rounds per family, per run. A gap that survives a Designer re-plan and
#: a fresh Developer call is a gap the model cannot close, and asking again is
#: how a stage turns into a hang.
REPLAN_ROUNDS = 1

#: Rounds of check -> route -> repair -> re-check, both within a stage and in
#: the cross-family reconciliation pass after the last one. Bounded because
#: route/repair/recheck is not bounded by the stage order, and unbounded on an
#: SLM it is a hang.
SELF_VALIDATION_BUDGET = 2


#: How many turns from the ceiling a loop starts counting down in the
#: observation channel. The budget is stated once in the system prompt and a
#: small model does not track it from there: without the countdown, 10 of 13
#: give-ups were "turn budget exhausted" and the single+graph arm spent every
#: turn reading on 6 of 7 stages without submitting (run single_20260831_160530).
#:
#: ONE number, and ONE wording (``loop.turns_left_hint``), because this is text
#: the model reads: at 2 turns on one arm and 3 on the other, with different
#: sentences, the countdown itself would be a second variable sitting on the
#: ``agent_mode`` axis.
TURNS_LEFT_WARNING = 3
