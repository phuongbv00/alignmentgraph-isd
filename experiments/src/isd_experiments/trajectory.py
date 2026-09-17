"""Re-score saved trajectories at a second tool-call cap.

The supervisor's Sprint-1 direction asks for TWO trajectory layers, not one:

* a **benchmark-comparable** layer at the evaluator's own cap of 20 tool calls,
  kept so the numbers stay comparable with the benchmark's original setup, with
  the limitation declared; and
* a **diagnostic** layer at a higher cap, because the cap is unfair to a
  decomposed system by construction. A ReAct agent makes ~5 calls and is seen
  whole; a decomposed harness makes 150-350 and only its opening is scored.

The essential property is that this re-scores SAVED trajectories offline. The
agent outputs are never regenerated, so adding the second layer costs no model
calls -- which is what makes it affordable after a run rather than a decision
that has to be made before one.

The benchmark's own scorer is left exactly as it is. The 20-call layer is its
answer and must stay comparable; the second layer belongs to the experiment,
which is why it lives here and not in the submodule.
"""

from __future__ import annotations

from pathlib import Path

#: The evaluator's own cap. Named, not repeated as a literal.
BENCHMARK_CAP = 20

#: The diagnostic cap. Provisional until measured against the call-count
#: distribution of a real run -- see the roadmap's phase 1.
DIAGNOSTIC_CAP = 120


def rescore(*, run_dirs=None, cap: int = DIAGNOSTIC_CAP, quiet: bool = False) -> int:
    """Re-score saved trajectories at ``cap`` and write them as a second layer.

    NOT IMPLEMENTED. The scaffolding is here because the roadmap makes this a
    gate before the official comparison run, and a stage with no home is a
    stage that gets forgotten. It is deliberately not faked: a function
    returning plausible numbers would let the roadmap's checklist be ticked
    without the work being done, which is worse than an honest gap.

    What it has to do when implemented:

    1. Read every ``<agent>_trajectory.json`` under the given run dirs.
    2. Score each with the evaluator's trajectory metric at ``cap``, through
       the same locked protocol the 20-call layer uses -- a second layer scored
       differently would not be comparable with the first.
    3. Write the result as a SEPARATE layer, never overwriting the
       benchmark-comparable scores.
    4. Record the cap in the output, so a reader always knows which layer a
       number came from.
    """
    raise SystemExit(
        "`trajectory rescore` is not implemented yet.\n"
        "  It is the roadmap's two-layer trajectory requirement, and it must be\n"
        "  settled BEFORE the official comparison run — the cap cannot change\n"
        "  after results are seen.\n"
        f"  Current layers: benchmark-comparable cap={BENCHMARK_CAP}, "
        f"diagnostic cap={cap} (planned)."
    )
