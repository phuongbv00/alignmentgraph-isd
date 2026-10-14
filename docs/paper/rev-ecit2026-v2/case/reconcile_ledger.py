"""Make the case run's violation ledger agree with its own final graph.

The ledger of run c0dbcb93 credits ``measurability|objective:ILO-02`` as
``repaired_by_harness``, while the final graph still flags ILO-02 for
measurability (``graph.json::node_violations``), the objective's statement is
unchanged and ``metadata.repair_metrics`` records no repair. The cause is in the
harness: ``Memory.settle`` closes every finding missing from the final
residual, and that residual holds only the violation types some family owns, so
an unowned finding still present at the last look is settled as repaired.
(Recorded for the journal paper in docs/paper/journal-code-fixes.md.)

Until the harness is fixed, the paper's case uses the ledger corrected by one
rule: a finding the final graph still flags on the same node is OPEN. Its
reason is ``unowned`` when no family owns the type. Nothing else is touched;
the run's output is unchanged. The original ledger is kept beside it as
``violations.raw.json``.

Usage:
  python3 reconcile_ledger.py <run dir> [<run dir> ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

#: Violation types no family owns (``repairs.OWNED_BY_FAMILY`` lists none of them).
UNOWNED = {"measurability"}


def reconcile(run: Path) -> int:
    raw = run / "violations.raw.json"
    src = raw if raw.exists() else run / "violations.json"
    ledger = json.loads(src.read_text(encoding="utf-8"))
    flagged = json.loads((run / "graph.json").read_text(encoding="utf-8")).get("node_violations") or {}
    changed = 0
    for f in ledger:
        still = f.get("type") in (flagged.get(f.get("node_id")) or [])
        if still and f.get("outcome") != "open":
            f.update(outcome="open", repaired_by="", repaired_at_round=0,
                     open_reason="unowned" if f.get("type") in UNOWNED else "unexplained")
            changed += 1
    if not raw.exists():
        raw.write_text((run / "violations.json").read_text(encoding="utf-8"), encoding="utf-8")
    (run / "violations.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(arg, "->", reconcile(Path(arg)), "finding(s) reopened")
